// k6 load test for Gate 2: 300 students start the same exam within ~90 s, then save answers.
//
//   k6 run -e BASE=https://<frontend-domain> -e EXAM_ID=12 -e PREFIX=LT -e PASSWORD=... loadtest/exam.js
//
// Prepare first: create 300 test students LT001..LT300 in one section (CSV import), log each in once to
// change the password (or set must_change_password=false for the test cohort), and schedule EXAM_ID for that
// section with no access code. Run against a staging copy, never against real students.
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.BASE || "http://127.0.0.1:3000";
const EXAM_ID = __ENV.EXAM_ID;
const PREFIX = __ENV.PREFIX || "LT";
const PASSWORD = __ENV.PASSWORD;
const saveErrors = new Counter("answer_save_errors");

export const options = {
  scenarios: {
    exam: { executor: "per-vu-iterations", vus: 300, iterations: 1, maxDuration: "20m", startTime: "0s" },
  },
  thresholds: {
    "http_req_duration{name:start}": ["p(95)<3000"],
    "http_req_duration{name:answer}": ["p(95)<800"],
    http_req_failed: ["rate<0.01"],
    answer_save_errors: ["count<10"],
  },
};

function csrf(jar) {
  const c = jar.cookiesForURL(BASE).csrftoken;
  return c ? c[0] : "";
}

export default function () {
  const jar = http.cookieJar();
  sleep(Math.random() * 90); // staggered arrival over ~1.5 minutes
  http.get(`${BASE}/api/v1/auth/csrf`);
  const user = `${PREFIX}${String(__VU).padStart(3, "0")}`;
  const json = () => ({ headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(jar) } });

  const login = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({ username: user, password: PASSWORD }), { ...json(), tags: { name: "login" } });
  if (!check(login, { "login 200": (r) => r.status === 200 })) return;

  const start = http.post(`${BASE}/api/v1/exams/${EXAM_ID}/start`, "{}", { ...json(), tags: { name: "start" } });
  if (!check(start, { "start ok": (r) => r.status === 200 || r.status === 201 })) return;
  const paper = start.json();

  for (const q of paper.questions) {
    sleep(5 + Math.random() * 20); // reading time
    let body = { flagged: false };
    if (q.options.length) body.options = [q.options[Math.floor(Math.random() * q.options.length)].id];
    else if (q.type === "numeric") body.value = String(Math.floor(Math.random() * 100));
    else body.text = "load test answer";
    const r = http.put(`${BASE}/api/v1/attempts/${paper.attempt_id}/answers/${q.id}`, JSON.stringify(body), { ...json(), tags: { name: "answer" } });
    if (r.status !== 200) saveErrors.add(1);
    if (Math.random() < 0.2) http.post(`${BASE}/api/v1/attempts/${paper.attempt_id}/events`, JSON.stringify({ type: "heartbeat" }), { ...json(), tags: { name: "heartbeat" } });
  }
  const submit = http.post(`${BASE}/api/v1/attempts/${paper.attempt_id}/submit`, "{}", { ...json(), tags: { name: "submit" } });
  check(submit, { "submitted": (r) => r.status === 200 });
}
