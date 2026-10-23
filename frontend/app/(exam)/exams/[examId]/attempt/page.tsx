"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";

import { Navigator, isAnswered } from "@/components/exam/navigator";
import { QuestionCard } from "@/components/exam/question-card";
import { Timer } from "@/components/exam/timer";
import { useAnswerQueue, type AnswerPayload } from "@/components/exam/use-answer-queue";
import { enterFullscreen, useFullscreenWatch, useProctor, type LiveState } from "@/components/exam/use-proctor";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { Alert, Spinner } from "@/components/ui/misc";
import { ApiError, get, post } from "@/lib/api";
import { cn, fmtDateTime } from "@/lib/format";
import { serverOffset } from "@/lib/hooks";
import type { AttemptState, PaperQuestion, UpcomingExam } from "@/lib/types";

type Phase = "loading" | "rules" | "running" | "submitted" | "error";

const SUBMIT_MESSAGES: Record<string, string> = {
  student: "Your answers have been submitted.",
  timeout: "Time is up. Your answers were submitted automatically.",
  fullscreen_limit: "You left full screen too many times, so your exam was submitted automatically.",
  admin: "Your exam was ended by the invigilator.",
};

/** Tiled, faint name + roll number over the paper so photos and screenshots are traceable. */
function Watermark({ text }: { text: string }) {
  const tiles = useMemo(() => Array.from({ length: 40 }), []);
  return (
    <div className="pointer-events-none fixed inset-0 z-0 grid select-none grid-cols-4 content-around overflow-hidden opacity-[0.06]" aria-hidden>
      {tiles.map((_, i) => (
        <span key={i} className="-rotate-[24deg] whitespace-nowrap py-10 text-center text-lg font-semibold">
          {text}
        </span>
      ))}
    </div>
  );
}

export default function AttemptPage({ params }: { params: Promise<{ examId: string }> }) {
  const { examId } = use(params);
  const [phase, setPhase] = useState<Phase>("loading");
  const [exam, setExam] = useState<UpcomingExam | null>(null);
  const [state, setState] = useState<AttemptState | null>(null);
  const [questions, setQuestions] = useState<PaperQuestion[]>([]);
  const [current, setCurrent] = useState(0);
  const [offset, setOffset] = useState(0);
  const [deadline, setDeadline] = useState<string | null>(null);
  const [submitReason, setSubmitReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState("");
  const [starting, setStarting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [notFullscreen, setNotFullscreen] = useState(false);
  const [exits, setExits] = useState(0);

  const attemptId = state?.attempt_id ?? null;
  const running = phase === "running";
  const simple = state?.simple_mode ?? false;

  const finish = useCallback((reason: string) => {
    setSubmitReason(reason);
    setPhase("submitted");
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
  }, []);

  const queue = useAnswerQueue(attemptId, useCallback((code: string) => finish(code === "time_over" ? "timeout" : "student"), [finish]));

  const onLive = useCallback(
    (s: LiveState) => {
      setOffset(serverOffset(s.server_time));
      setDeadline(s.deadline_at);
      setExits(s.fullscreen_exits);
      if (s.status === "submitted") {
        queue.clear();
        finish(s.submit_reason);
      }
    },
    [finish, queue],
  );
  useProctor(attemptId, running, onLive);
  useFullscreenWatch(attemptId, running && Boolean(state?.exam.require_fullscreen), () => setNotFullscreen(true), onLive);

  // Load: is there already an attempt for this exam?
  useEffect(() => {
    (async () => {
      try {
        const res = await get<{ results: UpcomingExam[] }>("/exams/upcoming");
        const found = res.results.find((e) => String(e.id) === examId) ?? null;
        if (!found) throw new ApiError(404, "not_found", "This exam is not available to you.");
        setExam(found);
        if (found.attempt?.status === "submitted") return finish("student");
        setPhase("rules");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load the exam.");
        setPhase("error");
      }
    })();
  }, [examId, finish]);

  // Warn before leaving mid-exam.
  useEffect(() => {
    if (!running) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [running]);

  function applyState(s: AttemptState) {
    setState(s);
    setOffset(serverOffset(s.server_time));
    setDeadline(s.deadline_at);
    setExits(s.fullscreen_exits);
    if (s.status === "submitted") return finish(s.submit_reason);
    setQuestions(s.questions ?? []);
    setPhase("running");
  }

  async function start() {
    setError(null);
    setStarting(true);
    // Full screen must be requested inside the click handler.
    if (exam?.require_fullscreen && !(await enterFullscreen())) {
      setStarting(false);
      return setError("Please allow full screen to start the exam.");
    }
    try {
      applyState(await post<AttemptState>(`/exams/${examId}/start`, code ? { access_code: code } : {}));
    } catch (e) {
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
      setError(e instanceof Error ? e.message : "Could not start the exam.");
    } finally {
      setStarting(false);
    }
  }

  function answer(q: PaperQuestion, patch: AnswerPayload) {
    const merged = { ...(q.answer ?? {}), ...patch };
    const flagged = patch.flagged ?? q.flagged;
    setQuestions((qs) => qs.map((x) => (x.id === q.id ? { ...x, answer: merged, flagged } : x)));
    const payload: AnswerPayload = { flagged };
    if (q.options.length) payload.options = merged.options ?? [];
    else if (q.type === "numeric") payload.value = merged.value ?? "";
    else payload.text = merged.text ?? "";
    queue.save(q.id, payload);
  }

  async function submit() {
    if (!attemptId) return;
    setSubmitting(true);
    await queue.flush();
    try {
      const res = await post<{ status: string; submit_reason: string }>(`/attempts/${attemptId}/submit`);
      queue.clear();
      finish(res.submit_reason || "student");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submit failed — your answers are saved. Try again.");
    } finally {
      setSubmitting(false);
      setConfirmOpen(false);
    }
  }

  const onExpire = useCallback(() => {
    // The server auto-submits too; this just tells it now and shows the right screen.
    if (attemptId) void queue.flush().then(() => post(`/attempts/${attemptId}/submit`).catch(() => undefined));
    queue.clear();
    finish("timeout");
  }, [attemptId, finish, queue]);

  // ---- Screens ----------------------------------------------------------------------------------

  if (phase === "loading") return <Spinner label="Loading exam…" />;

  if (phase === "error")
    return (
      <Centered>
        <Alert>{error}</Alert>
        <Link href="/exams" className="mt-4 inline-block text-sm text-primary">← Back to exams</Link>
      </Centered>
    );

  if (phase === "submitted")
    return (
      <Centered>
        <Card>
          <CardBody className="py-10 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-success-soft text-2xl text-success">✓</div>
            <h1 className="text-xl font-semibold">Submitted</h1>
            <p className="mt-2 text-muted">{SUBMIT_MESSAGES[submitReason] ?? SUBMIT_MESSAGES.student}</p>
            <p className="mt-1 text-sm text-muted">Your result will appear once your teacher publishes it.</p>
            <Link href="/exams" className="mt-6 inline-block">
              <Button>Back to exams</Button>
            </Link>
          </CardBody>
        </Card>
      </Centered>
    );

  if (phase === "rules" && exam)
    return (
      <Centered wide>
        <Card>
          <CardBody className="space-y-5 py-6">
            <div>
              <p className="text-sm text-muted">{exam.subject}</p>
              <h1 className="text-2xl font-semibold">{exam.title}</h1>
              <p className="text-sm text-muted">
                {exam.duration_min} minutes · {exam.total_marks} marks · closes {fmtDateTime(exam.end_at)}
              </p>
            </div>
            {exam.instructions && <div className="whitespace-pre-line rounded-lg bg-subtle p-4 text-sm">{exam.instructions}</div>}
            <ul className="list-disc space-y-1 pl-5 text-sm">
              <li>The timer is kept by the school server. Closing the page or going offline does not pause it.</li>
              <li>Each answer is saved as soon as you choose it. You can change it until you submit.</li>
              {exam.require_fullscreen && <li>The exam runs in full screen. Leaving full screen is recorded{exam.attempt ? "" : " and may end your exam"}.</li>}
              <li>Switching tabs or windows, copying and pasting are recorded and shown to your teacher.</li>
              <li>You can use this exam on one device only.</li>
            </ul>
            {exam.needs_access_code && !exam.attempt && (
              <Field label="Exam access code" hint="Your invigilator will read this out.">
                <Input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" className="max-w-48 uppercase" />
              </Field>
            )}
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4" />
              I have read the rules and will do this exam on my own.
            </label>
            <Alert>{error}</Alert>
            <div className="flex items-center justify-between gap-3">
              <Link href="/exams" className="text-sm text-muted">Cancel</Link>
              <Button size="lg" onClick={start} disabled={!consent || exam.status !== "live"} loading={starting}>
                {exam.attempt ? "Resume exam" : exam.status === "live" ? "Start exam" : "Not open yet"}
              </Button>
            </div>
          </CardBody>
        </Card>
      </Centered>
    );

  const q = questions[current];
  const answered = questions.filter(isAnswered).length;
  const flagged = questions.filter((x) => x.flagged).length;

  return (
    <div className="exam-locked relative min-h-screen bg-background">
      {state && <Watermark text={state.watermark} />}
      <header className="sticky top-0 z-20 border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{state?.exam.title}</p>
            <p className="text-xs text-muted">
              {answered}/{questions.length} answered
              {queue.pending > 0 && ` · saving ${queue.pending}…`}
              {queue.offline && <span className="font-medium text-danger"> · offline — answers will be sent when you reconnect</span>}
            </p>
          </div>
          {deadline && <Timer deadline={deadline} offsetMs={offset} onExpire={onExpire} large={simple} />}
          <Button variant="success" size={simple ? "lg" : "md"} onClick={() => setConfirmOpen(true)}>
            Submit
          </Button>
        </div>
      </header>

      <main className="relative z-10 mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[1fr_260px]">
        <Card>
          <CardBody className="py-6">
            {q ? (
              <>
                <QuestionCard key={q.id} q={q} onAnswer={(p) => answer(q, p)} large={simple} />
                <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
                  <Button variant="outline" size={simple ? "xl" : "md"} disabled={current === 0} onClick={() => setCurrent(current - 1)}>
                    ← Previous
                  </Button>
                  <Button
                    variant="ghost"
                    size={simple ? "lg" : "md"}
                    onClick={() => answer(q, { flagged: !q.flagged })}
                    className={cn(q.flagged && "bg-warning-soft text-warning")}
                  >
                    {q.flagged ? "★ Marked for review" : "☆ Mark for review"}
                  </Button>
                  {current < questions.length - 1 ? (
                    <Button size={simple ? "xl" : "md"} onClick={() => setCurrent(current + 1)}>
                      Next →
                    </Button>
                  ) : (
                    <Button variant="success" size={simple ? "xl" : "md"} onClick={() => setConfirmOpen(true)}>
                      Finish
                    </Button>
                  )}
                </div>
              </>
            ) : (
              <Spinner />
            )}
          </CardBody>
        </Card>
        <aside>
          <Card>
            <CardBody>
              <Navigator questions={questions} current={current} onGo={setCurrent} large={simple} />
            </CardBody>
          </Card>
          <Alert className="mt-4">{error}</Alert>
        </aside>
      </main>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Submit your exam?"
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>Keep working</Button>
            <Button variant="success" onClick={submit} loading={submitting}>Submit now</Button>
          </>
        }
      >
        <div className="space-y-2 text-sm">
          <p>You have answered <b>{answered}</b> of <b>{questions.length}</b> questions.</p>
          {questions.length - answered > 0 && <p className="text-warning">{questions.length - answered} question(s) are not answered.</p>}
          {flagged > 0 && <p className="text-warning">{flagged} question(s) are marked for review.</p>}
          <p className="text-muted">After you submit you cannot change your answers.</p>
        </div>
      </Dialog>

      {notFullscreen && state?.exam.require_fullscreen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6">
          <Card className="max-w-md">
            <CardBody className="space-y-4 py-6 text-center">
              <h2 className="text-lg font-semibold">You left full screen</h2>
              <p className="text-sm text-muted">This has been recorded. Return to full screen to continue.</p>
              {state.exam.max_fullscreen_exits > 0 && (
                <p className="text-sm font-medium text-danger">
                  Warning {exits} of {state.exam.max_fullscreen_exits}: at {state.exam.max_fullscreen_exits} your exam is submitted automatically.
                </p>
              )}
              <Button
                size="lg"
                onClick={async () => {
                  if (await enterFullscreen()) setNotFullscreen(false);
                }}
              >
                Return to full screen
              </Button>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}

function Centered({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return <main className={cn("mx-auto px-4 py-16", wide ? "max-w-2xl" : "max-w-md")}>{children}</main>;
}
