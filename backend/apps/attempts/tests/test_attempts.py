import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from apps.attempts.models import Attempt, AttemptAnswer, ProctorEvent
from apps.exams.models import Question
from conftest import Browser, build_exam

pytestmark = pytest.mark.django_db


def start(b, exam, data=None, **extra):
    return b.post(f"/api/v1/exams/{exam.pk}/start", data or {}, **extra)


def tokens_for(paper, question):
    """Map option text → token for one question in the student's paper."""
    item = next(q for q in paper["questions"] if q["id"] == question.pk)
    return {o["text"]: o["id"] for o in item["options"]}


# --- The paper never leaks the key ----------------------------------------------------------------


def test_start_payload_has_no_answer_key(student_browser, live_exam, bank):
    r = start(student_browser, live_exam)
    assert r.status_code == 201, r.content
    raw = r.content.decode()
    for leak in ["is_correct", "explanation", "numeric_answer", "numeric_tolerance", "3.14", "correct"]:
        assert leak not in raw, leak
    option_ids = {str(o.pk) for q in bank.values() for o in q.options.all()}
    for q in r.json()["questions"]:
        for opt in q["options"]:
            assert opt["id"] not in option_ids and len(opt["id"]) == 8


def test_option_tokens_differ_between_students(live_exam, student, student2, bank):
    a, b = Browser(), Browser()
    a.login(student.username)
    b.login(student2.username)
    ta = tokens_for(start(a, live_exam).json(), bank["mcq1"])
    tb = tokens_for(start(b, live_exam).json(), bank["mcq1"])
    assert set(ta) == set(tb) == {"3", "4", "5"}
    assert ta != tb


# --- Who can start, and when ----------------------------------------------------------------------


def test_untargeted_section_and_other_class_cannot_see_exam(live_exam, student_8b, student_9a):
    for user in (student_8b, student_9a):
        b = Browser()
        b.login(user.username)
        assert start(b, live_exam).status_code == 404
        assert all(e["id"] != live_exam.pk for e in b.get("/api/v1/exams/upcoming").json()["results"])


def test_not_open_yet_and_closed(student_browser, structure, bank):
    upcoming = build_exam(structure, start_offset=30, end_offset=90)
    r = start(student_browser, upcoming)
    assert r.status_code == 403 and r.json()["code"] == "not_open"
    closed = build_exam(structure, rule={"easy": 1}, pass_marks="0")
    closed.end_at = timezone.now() - timedelta(minutes=1)
    closed.save()
    r = start(student_browser, closed)
    assert r.status_code == 403 and r.json()["code"] == "closed"


def test_draft_exam_is_invisible(student_browser, structure, bank):
    draft = build_exam(structure, do_schedule=False)
    assert start(student_browser, draft).status_code == 404


def test_access_code(student_browser, structure, bank):
    exam = build_exam(structure, settings={"access_code": "TIGER7"})
    assert start(student_browser, exam, {"access_code": "wrong"}).json()["code"] == "access_code"
    assert start(student_browser, exam, {"access_code": "tiger7"}).status_code == 201


def test_ip_allowlist(student_browser, structure, bank):
    exam = build_exam(structure, settings={"ip_allowlist": ["10.0.0.0/8"]})
    assert start(student_browser, exam).json()["code"] == "ip_not_allowed"
    r = start(student_browser, exam, REMOTE_ADDR="10.1.2.3")
    assert r.status_code == 201, r.json()


def test_deadline_is_capped_by_window_end(student_browser, structure, bank):
    exam = build_exam(structure, end_offset=10, duration=60)
    body = start(student_browser, exam).json()
    deadline = Attempt.objects.get(pk=body["attempt_id"]).deadline_at
    assert abs((deadline - exam.end_at).total_seconds()) < 1


# --- One attempt, one device ----------------------------------------------------------------------


def test_second_start_resumes_the_same_attempt(student_browser, live_exam):
    first = start(student_browser, live_exam)
    second = start(student_browser, live_exam)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["attempt_id"] == second.json()["attempt_id"]
    assert [q["id"] for q in first.json()["questions"]] == [q["id"] for q in second.json()["questions"]]
    assert Attempt.objects.filter(exam=live_exam).count() == 1


def test_second_device_is_blocked_and_flagged(live_exam, student):
    a, b = Browser(), Browser()
    a.login(student.username)
    b.login(student.username)
    attempt_id = start(a, live_exam).json()["attempt_id"]
    r = start(b, live_exam)
    assert r.status_code == 409 and r.json()["code"] == "other_device"
    assert b.get(f"/api/v1/attempts/{attempt_id}").status_code == 409
    attempt = Attempt.objects.get(pk=attempt_id)
    assert attempt.events.filter(type=ProctorEvent.Type.SECOND_LOGIN).count() == 2
    assert attempt.flag_count == 2


def test_admin_can_release_device(live_exam, student, admin_browser):
    a, b = Browser(), Browser()
    a.login(student.username)
    b.login(student.username)
    attempt_id = start(a, live_exam).json()["attempt_id"]
    assert admin_browser.post(f"/api/v1/admin/attempts/{attempt_id}/release-device", {"reason": "laptop died"}).status_code == 200
    assert start(b, live_exam).status_code == 200
    assert start(a, live_exam).status_code == 409


def test_student_cannot_touch_another_students_attempt(live_exam, student, student2, bank):
    a, b = Browser(), Browser()
    a.login(student.username)
    b.login(student2.username)
    attempt_id = start(a, live_exam).json()["attempt_id"]
    assert b.get(f"/api/v1/attempts/{attempt_id}").status_code == 404
    assert b.put(f"/api/v1/attempts/{attempt_id}/answers/{bank['mcq1'].pk}", {"options": []}).status_code == 404
    assert b.post(f"/api/v1/attempts/{attempt_id}/submit").status_code == 404
    assert b.post(f"/api/v1/attempts/{attempt_id}/events", {"type": "heartbeat"}).status_code == 404


# --- Answers and the server clock -----------------------------------------------------------------


def test_save_answer_and_resume_restores_it(student_browser, live_exam, bank):
    paper = start(student_browser, live_exam).json()
    aid, tok = paper["attempt_id"], tokens_for(paper, bank["mcq1"])
    r = student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['mcq1'].pk}", {"options": [tok["4"]], "flagged": True})
    assert r.status_code == 200, r.content
    stored = AttemptAnswer.objects.get(attempt_id=aid, question=bank["mcq1"])
    correct_id = bank["mcq1"].options.get(text="4").pk
    assert stored.answer == {"options": [correct_id]}  # stored as option ids, not tokens
    resumed = student_browser.get(f"/api/v1/attempts/{aid}").json()
    item = next(q for q in resumed["questions"] if q["id"] == bank["mcq1"].pk)
    assert item["answer"] == {"options": [tok["4"]]} and item["flagged"] is True


def test_answer_validation(student_browser, live_exam, bank):
    paper = start(student_browser, live_exam).json()
    aid = paper["attempt_id"]
    tok = tokens_for(paper, bank["mcq1"])
    url = f"/api/v1/attempts/{aid}/answers/{bank['mcq1'].pk}"
    assert student_browser.put(url, {"options": ["forged00"]}).status_code == 400
    assert student_browser.put(url, {"options": [tok["3"], tok["4"]]}).status_code == 400  # single-answer
    other_q = Question.objects.create(subject=bank["mcq1"].subject, chapter=bank["mcq1"].chapter, type="numeric", text="x", numeric_answer=1)
    assert student_browser.put(f"/api/v1/attempts/{aid}/answers/{other_q.pk}", {"value": "1"}).status_code == 404


def test_answer_after_deadline_is_rejected_and_auto_submits(student_browser, live_exam, bank):
    paper = start(student_browser, live_exam).json()
    aid = paper["attempt_id"]
    Attempt.objects.filter(pk=aid).update(deadline_at=timezone.now() - timedelta(seconds=settings.EXAM_GRACE_SECONDS + 1))
    r = student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['num'].pk}", {"value": "3.14"})
    assert r.status_code == 409 and r.json()["code"] == "time_over"
    attempt = Attempt.objects.get(pk=aid)
    assert attempt.status == "submitted" and attempt.submit_reason == "timeout"
    assert attempt.events.filter(type="late_answer").exists()  # logged even though the request was refused
    assert not AttemptAnswer.objects.filter(attempt_id=aid, question=bank["num"]).exists()


def test_answer_inside_grace_period_is_accepted(student_browser, live_exam, bank):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    Attempt.objects.filter(pk=aid).update(deadline_at=timezone.now() - timedelta(seconds=settings.EXAM_GRACE_SECONDS - 5))
    r = student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['num'].pk}", {"value": "3.14"})
    assert r.status_code == 200


def test_submitted_attempt_is_read_only_and_submit_is_idempotent(student_browser, live_exam, bank):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    r1 = student_browser.post(f"/api/v1/attempts/{aid}/submit")
    r2 = student_browser.post(f"/api/v1/attempts/{aid}/submit")
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["submitted_at"] == r2.json()["submitted_at"]
    assert "score" not in r1.json()  # hidden until published
    r = student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['num'].pk}", {"value": "3.14"})
    assert r.status_code == 409 and r.json()["code"] == "submitted"
    assert "questions" not in student_browser.get(f"/api/v1/attempts/{aid}").json()


def test_ip_change_is_flagged(student_browser, live_exam, bank):
    aid = start(student_browser, live_exam, REMOTE_ADDR="10.0.0.1").json()["attempt_id"]
    student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['num'].pk}", {"value": "1"}, REMOTE_ADDR="10.0.0.2")
    student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['num'].pk}", {"value": "2"}, REMOTE_ADDR="10.0.0.2")
    assert ProctorEvent.objects.filter(attempt_id=aid, type="ip_change").count() == 1


# --- Grading ----------------------------------------------------------------------------------------


def test_grading_all_question_types(student_browser, live_exam, bank):
    paper = start(student_browser, live_exam).json()
    aid = paper["attempt_id"]
    put = lambda q, body: student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank[q].pk}", body)  # noqa: E731
    put("mcq1", {"options": [tokens_for(paper, bank["mcq1"])["5"]]})  # wrong: -0.25
    put("mcq2", {"options": [tokens_for(paper, bank["mcq2"])["6"]]})  # right: +1
    m = tokens_for(paper, bank["multi"])
    put("multi", {"options": [m["2"], m["4"]]})  # exact set: +2
    put("tf", {"options": [tokens_for(paper, bank["tf"])["False"]]})  # right: +1
    put("num", {"value": "3.141"})  # within tolerance: +2
    put("short", {"text": "p/q where q != 0"})  # manual
    student_browser.post(f"/api/v1/attempts/{aid}/submit")
    attempt = Attempt.objects.get(pk=aid)
    assert attempt.score == Decimal("5.75")
    assert attempt.max_score == Decimal("10")
    assert attempt.grading_status == "pending_manual"
    short = AttemptAnswer.objects.get(attempt=attempt, question=bank["short"])
    assert short.is_correct is None and short.marks_awarded is None


def test_partial_multi_select_is_wrong(student_browser, live_exam, bank):
    paper = start(student_browser, live_exam).json()
    aid = paper["attempt_id"]
    student_browser.put(f"/api/v1/attempts/{aid}/answers/{bank['multi'].pk}", {"options": [tokens_for(paper, bank["multi"])["2"]]})
    student_browser.post(f"/api/v1/attempts/{aid}/submit")
    ans = AttemptAnswer.objects.get(attempt_id=aid, question=bank["multi"])
    assert ans.is_correct is False and ans.marks_awarded == 0


# --- Proctoring ----------------------------------------------------------------------------------


def test_events_are_logged_and_counted(student_browser, live_exam):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    for t in ["tab_switch", "paste", "offline", "heartbeat"]:
        assert student_browser.post(f"/api/v1/attempts/{aid}/events", {"type": t}).status_code == 200
    attempt = Attempt.objects.get(pk=aid)
    assert set(attempt.events.values_list("type", flat=True)) == {"tab_switch", "paste", "offline"}
    assert attempt.flag_count == 2  # offline is logged but not a flag
    assert student_browser.post(f"/api/v1/attempts/{aid}/events", {"type": "second_login"}).status_code == 400


def test_fullscreen_exit_limit_auto_submits(student_browser, structure, bank):
    exam = build_exam(structure, settings={"max_fullscreen_exits": 2})
    aid = start(student_browser, exam).json()["attempt_id"]
    r1 = student_browser.post(f"/api/v1/attempts/{aid}/events", {"type": "fullscreen_exit"}).json()
    assert r1["status"] == "in_progress" and r1["fullscreen_exits"] == 1
    r2 = student_browser.post(f"/api/v1/attempts/{aid}/events", {"type": "fullscreen_exit"}).json()
    assert r2["status"] == "submitted" and r2["submit_reason"] == "fullscreen_limit"


def test_heartbeat_reports_admin_extension(student_browser, live_exam, admin_browser):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    before = Attempt.objects.get(pk=aid).deadline_at
    r = admin_browser.post(f"/api/v1/admin/attempts/{aid}/extend", {"minutes": 5, "reason": "power cut"})
    assert r.status_code == 200
    beat = student_browser.post(f"/api/v1/attempts/{aid}/events", {"type": "heartbeat"}).json()
    from django.utils.dateparse import parse_datetime

    assert parse_datetime(beat["deadline_at"]) == before + timedelta(minutes=5)


def test_interventions_need_reason(admin_browser, student_browser, live_exam):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    assert admin_browser.post(f"/api/v1/admin/attempts/{aid}/terminate", {}).status_code == 400
    r = admin_browser.post(f"/api/v1/admin/attempts/{aid}/terminate", {"reason": "caught with phone"})
    assert r.status_code == 200
    assert Attempt.objects.get(pk=aid).submit_reason == "admin"


def test_reset_lets_student_retake(admin_browser, student_browser, live_exam):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    student_browser.post(f"/api/v1/attempts/{aid}/submit")
    assert admin_browser.post(f"/api/v1/admin/attempts/{aid}/reset", {"reason": "wrong paper"}).status_code == 200
    assert start(student_browser, live_exam).status_code == 201


# --- Cron ------------------------------------------------------------------------------------------


def test_sweep_requires_secret_and_auto_submits(student_browser, live_exam):
    aid = start(student_browser, live_exam).json()["attempt_id"]
    Attempt.objects.filter(pk=aid).update(deadline_at=timezone.now() - timedelta(minutes=1))
    anon = Browser()
    assert anon.post("/api/v1/internal/sweep-attempts").status_code in (401, 403)
    assert anon.post("/api/v1/internal/sweep-attempts", HTTP_X_INTERNAL_SECRET="wrong").status_code in (401, 403)
    r = anon.post("/api/v1/internal/sweep-attempts", HTTP_X_INTERNAL_SECRET=settings.INTERNAL_CRON_SECRET)
    assert r.status_code == 200 and r.json()["auto_submitted"] == 1
    assert Attempt.objects.get(pk=aid).status == "submitted"


def test_warmup_is_public_and_cheap(db):
    r = Browser().get("/api/v1/internal/warmup")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_monitor_shows_every_targeted_student(admin_browser, student_browser, student2, live_exam):
    start(student_browser, live_exam)
    r = admin_browser.get(f"/api/v1/admin/exams/{live_exam.pk}/monitor")
    assert r.status_code == 200
    states = {row["roll_no"]: row["state"] for row in r.json()["students"]}
    assert states == {"8A01": "in_progress", "8A02": "not_started"}
    Attempt.objects.update(last_seen_at=timezone.now() - timedelta(minutes=5))
    rows = admin_browser.get(f"/api/v1/admin/exams/{live_exam.pk}/monitor").json()["students"]
    assert {r["roll_no"]: r["state"] for r in rows}["8A01"] == "disconnected"


def test_api_responses_are_not_cached(student_browser, live_exam):
    r = start(student_browser, live_exam)
    assert r["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in r["Content-Security-Policy"]
    json.loads(r.content)
