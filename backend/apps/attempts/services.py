"""Exam attempt lifecycle. Every rule here is enforced server-side; the browser only deters and reports."""

import hashlib
import random
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.core.storage import get_storage
from apps.core.utils import client_ip, ip_in_allowlist, random_token
from apps.exams.models import Exam, ExamQuestion, Question

from .grading import grade_attempt, refresh_exam_grading_state
from .models import UNFLAGGED_EVENT_TYPES, Attempt, AttemptAnswer, ProctorEvent

_rng = random.SystemRandom()
MAX_SHORT_ANSWER = 5000
MAX_NUMERIC_LEN = 32


class AttemptError(Exception):
    """Business-rule refusal: carries an HTTP status and a stable machine-readable code."""

    def __init__(self, status, code, detail, extra=None):
        super().__init__(detail)
        self.status, self.code, self.detail, self.extra = status, code, detail, extra or {}

    def payload(self):
        return {"detail": self.detail, "code": self.code, **self.extra}


def grace():
    return timedelta(seconds=settings.EXAM_GRACE_SECONDS)


def device_of(request):
    return request.COOKIES.get(settings.DEVICE_COOKIE, "")


# --- Eligibility -----------------------------------------------------------------------------------


def exams_for_student(user):
    """Scheduled exams that target the student's own section."""
    profile = user.student_profile
    return Exam.objects.filter(targets__section_id=profile.section_id, status__in=[Exam.Status.SCHEDULED, Exam.Status.GRADED, Exam.Status.PUBLISHED]).select_related("subject")


def _check_seb(request, exam):
    if not exam.setting("require_seb"):
        return
    key = exam.setting("seb_config_key") or ""
    provided = request.headers.get("X-SafeExamBrowser-ConfigKeyHash", "")
    url = settings.PUBLIC_ORIGIN.rstrip("/") + request.get_full_path() if settings.PUBLIC_ORIGIN else request.build_absolute_uri()
    expected = hashlib.sha256((url + key).encode()).hexdigest()
    if not key or not constant_time_compare(provided.lower(), expected):
        raise AttemptError(403, "seb_required", "This exam must be taken in Safe Exam Browser.")


def _check_network(request, exam):
    allowlist = exam.setting("ip_allowlist") or []
    if allowlist and not ip_in_allowlist(client_ip(request), allowlist):
        raise AttemptError(403, "ip_not_allowed", "This exam can only be taken from the school network.")


# --- Paper -----------------------------------------------------------------------------------------


def build_question_order(exam):
    """Per-attempt paper: per-student draws, shuffled questions within each part, shuffled options with
    random per-attempt tokens. Stored on the attempt so resume shows exactly the same paper."""
    shuffle_q = exam.setting("shuffle_questions")
    shuffle_o = exam.setting("shuffle_options")
    eqs = list(ExamQuestion.objects.filter(exam=exam).select_related("part", "question").prefetch_related("question__options"))
    by_part = defaultdict(list)
    parts = {}
    for eq in eqs:
        by_part[eq.part_id].append(eq)
        parts[eq.part_id] = eq.part

    order = []
    for part in sorted(parts.values(), key=lambda p: (p.order, p.id)):
        chosen = by_part[part.id]
        if part.per_student:
            pools = defaultdict(list)
            for eq in chosen:
                pools[eq.question.difficulty].append(eq)
            chosen = []
            for difficulty, n in part.rule_counts().items():
                if n:
                    chosen.extend(_rng.sample(pools[difficulty], n))
        else:
            chosen = sorted(chosen, key=lambda eq: (eq.order, eq.id))
        if shuffle_q:
            _rng.shuffle(chosen)
        for eq in chosen:
            options = list(eq.question.options.all())
            if shuffle_o and eq.question.type != Question.Type.TRUE_FALSE:
                _rng.shuffle(options)
            used, opts = set(), []
            for opt in options:
                token = random_token(8)
                while token in used:
                    token = random_token(8)
                used.add(token)
                opts.append([token, opt.pk])
            order.append({"q": eq.question_id, "part": part.id, "marks": str(eq.marks), "opts": opts})
    return order


def paper_payload(attempt):
    """What the student's browser receives: text and option tokens only. No keys, no explanations."""
    ids = [item["q"] for item in attempt.question_order]
    questions = {q.pk: q for q in Question.objects.filter(pk__in=ids).prefetch_related("options")}
    parts = {p.pk: p for p in attempt.exam.parts.all()}
    answers = {a.question_id: a for a in attempt.answers.all()}
    storage = get_storage()
    remaining = max(0, int((attempt.deadline_at - timezone.now()).total_seconds()))
    url_ttl = remaining + settings.EXAM_GRACE_SECONDS + 300

    items = []
    for index, item in enumerate(attempt.question_order, start=1):
        q = questions[item["q"]]
        text_by_id = {o.pk: o.text for o in q.options.all()}
        token_by_id = {opt_id: token for token, opt_id in item["opts"]}
        saved = answers.get(q.pk)
        saved_answer = None
        if saved is not None:
            saved_answer = {k: v for k, v in saved.answer.items() if k != "options"}
            if "options" in saved.answer:
                saved_answer["options"] = [token_by_id[i] for i in saved.answer["options"] if i in token_by_id]
        part = parts.get(item["part"])
        items.append(
            {
                "number": index,
                "id": q.pk,
                "part": part.name if part else "",
                "part_instructions": part.instructions if part else "",
                "type": q.type,
                "text": q.text,
                "image_url": storage.download_url(q.image_key, url_ttl) if q.image_key else None,
                "marks": item["marks"],
                "negative_marks": str(q.negative_marks),
                "options": [{"id": token, "text": text_by_id[opt_id]} for token, opt_id in item["opts"]],
                "answer": saved_answer,
                "flagged": saved.flagged if saved else False,
            }
        )
    return items


def attempt_state(attempt, request=None, include_paper=True):
    exam = attempt.exam
    profile = attempt.student.student_profile
    data = {
        "attempt_id": attempt.pk,
        "status": attempt.status,
        "submit_reason": attempt.submit_reason,
        "server_time": timezone.now(),
        "started_at": attempt.started_at,
        "deadline_at": attempt.deadline_at,
        "submitted_at": attempt.submitted_at,
        "exam": {
            "id": exam.pk,
            "title": exam.title,
            "subject": exam.subject.name,
            "instructions": exam.instructions,
            "duration_min": exam.duration_min,
            "total_marks": str(attempt.max_score or exam.total_marks),
            "require_fullscreen": exam.setting("require_fullscreen"),
            "max_fullscreen_exits": exam.setting("max_fullscreen_exits"),
        },
        "fullscreen_exits": attempt.fullscreen_exits,
        "watermark": f"{attempt.student.full_name} · {profile.roll_no}",
        "simple_mode": profile.school_class.simple_mode,
    }
    if include_paper and attempt.is_open:
        data["questions"] = paper_payload(attempt)
    return data


# --- Start / resume --------------------------------------------------------------------------------


def enforce_device(request, attempt):
    """One device per attempt. The first device to start (or the first after an admin release) owns it."""
    device = device_of(request)
    if not device:
        raise AttemptError(400, "device_cookie_missing", "Your browser blocked a required cookie. Log in again.")
    if not attempt.device_id:
        Attempt.objects.filter(pk=attempt.pk, device_id="").update(device_id=device)
        attempt.refresh_from_db(fields=["device_id"])
    if not constant_time_compare(attempt.device_id, device):
        record_event(attempt, ProctorEvent.Type.SECOND_LOGIN, {"ip": client_ip(request)})
        raise AttemptError(409, "other_device", "This exam is already open on another device. Ask the invigilator for help.")


def _check_ip(request, attempt):
    ip = client_ip(request)
    if attempt.ip and ip and ip != attempt.ip:
        recent = attempt.events.filter(type=ProctorEvent.Type.IP_CHANGE, detail__ip=ip).exists()
        if not recent:
            record_event(attempt, ProctorEvent.Type.IP_CHANGE, {"ip": ip, "previous": attempt.ip})


def start_attempt(request, exam_id):
    user = request.user
    profile = user.student_profile
    exam = exams_for_student(user).filter(pk=exam_id).first()
    if exam is None:
        raise AttemptError(404, "not_found", "Exam not found.")

    existing = Attempt.objects.filter(exam=exam, student=user).select_related("exam__subject").first()
    if existing is not None:
        return resume(request, existing), False

    now = timezone.now()
    status = exam.effective_status
    if status == "upcoming":
        raise AttemptError(403, "not_open", "This exam has not started yet.", {"start_at": exam.start_at.isoformat()})
    if status != "live":
        raise AttemptError(403, "closed", "This exam is closed.")
    access_code = (exam.setting("access_code") or "").strip()
    if access_code:
        provided = str(request.data.get("access_code", "")).strip()
        if not constant_time_compare(provided.upper(), access_code.upper()):
            raise AttemptError(403, "access_code", "Incorrect exam access code.")
    _check_network(request, exam)
    _check_seb(request, exam)
    device = device_of(request)
    if not device:
        raise AttemptError(400, "device_cookie_missing", "Your browser blocked a required cookie. Log in again.")

    order = build_question_order(exam)
    deadline = min(now + timedelta(minutes=exam.duration_min), exam.end_at)
    try:
        with transaction.atomic():
            attempt = Attempt.objects.create(
                exam=exam,
                student=user,
                section_id=profile.section_id,
                started_at=now,
                deadline_at=deadline,
                question_order=order,
                max_score=sum((Decimal(i["marks"]) for i in order), Decimal("0")),
                ip=client_ip(request) or None,
                user_agent=request.headers.get("User-Agent", "")[:400],
                device_id=device,
                last_seen_at=now,
            )
    except IntegrityError:
        # Two tabs/devices raced to start; the unique (exam, student) constraint let only one win.
        attempt = Attempt.objects.get(exam=exam, student=user)
        return resume(request, attempt), False
    return attempt, True


def load_attempt(request, attempt_id):
    """Always scoped to request.user: a student can never load someone else's attempt by changing the id."""
    qs = Attempt.objects.select_related("exam__subject", "student__student_profile__school_class")
    attempt = qs.filter(pk=attempt_id, student=request.user).first()
    if attempt is None:
        raise AttemptError(404, "not_found", "Attempt not found.")
    return attempt


def resume(request, attempt):
    expire_if_due(attempt)
    if attempt.is_open:
        enforce_device(request, attempt)
        _check_network(request, attempt.exam)
        touch(attempt)
    return attempt


def touch(attempt):
    now = timezone.now()
    Attempt.objects.filter(pk=attempt.pk).update(last_seen_at=now)
    attempt.last_seen_at = now


# --- Answers ---------------------------------------------------------------------------------------


def _normalise_answer(question, entry, data):
    """Validate the browser's answer and translate option tokens back to option ids."""
    qtype = question.type
    if qtype in Question.OPTION_TYPES:
        tokens = data.get("options", [])
        if not isinstance(tokens, list) or len(tokens) > 8:
            raise AttemptError(400, "invalid_answer", "Invalid options.")
        mapping = dict(entry["opts"])
        if any(not isinstance(t, str) or t not in mapping for t in tokens):
            raise AttemptError(400, "invalid_answer", "Unknown option.")
        ids = sorted({mapping[t] for t in tokens})
        if qtype != Question.Type.MCQ_MULTI and len(ids) > 1:
            raise AttemptError(400, "invalid_answer", "Choose only one option.")
        return {"options": ids}
    if qtype == Question.Type.NUMERIC:
        value = data.get("value", "")
        value = "" if value is None else str(value).strip()
        if len(value) > MAX_NUMERIC_LEN:
            raise AttemptError(400, "invalid_answer", "Number is too long.")
        return {"value": value}
    text = data.get("text", "")
    if not isinstance(text, str) or len(text) > MAX_SHORT_ANSWER:
        raise AttemptError(400, "invalid_answer", f"Answer must be text of at most {MAX_SHORT_ANSWER} characters.")
    return {"text": text}


def save_answer(request, attempt_id, question_id, data):
    # Checks that log events or auto-submit run outside the transaction so a refusal cannot roll them back.
    attempt = load_attempt(request, attempt_id)
    if not attempt.is_open:
        raise AttemptError(409, "submitted", "This attempt has already been submitted.")
    if timezone.now() > attempt.deadline_at + grace():
        record_event(attempt, ProctorEvent.Type.LATE_ANSWER, {"question": question_id})
        submit(attempt, Attempt.SubmitReason.TIMEOUT)
        raise AttemptError(409, "time_over", "Time is over. Your answers up to the deadline were submitted.")
    enforce_device(request, attempt)
    _check_network(request, attempt.exam)
    _check_ip(request, attempt)

    entry = attempt.entry(question_id)
    if entry is None:
        raise AttemptError(404, "not_found", "Question is not part of this attempt.")
    question = Question.objects.prefetch_related("options").get(pk=question_id)
    answer = _normalise_answer(question, entry, data)
    flagged = bool(data.get("flagged", False))

    with transaction.atomic():
        locked = Attempt.objects.select_for_update().get(pk=attempt.pk)
        now = timezone.now()
        # Re-check under the row lock: a submit or sweep may have landed since the checks above.
        if not locked.is_open:
            raise AttemptError(409, "submitted", "This attempt has already been submitted.")
        if now > locked.deadline_at + grace():
            raise AttemptError(409, "time_over", "Time is over.")
        row = AttemptAnswer.objects.filter(attempt=locked, question=question).first()
        if row is None:
            AttemptAnswer.objects.create(attempt=locked, question=question, answer=answer, flagged=flagged, answered_at=now)
        else:
            changed = row.answer != answer
            row.flagged = flagged
            if changed:
                row.answer = answer
                row.answered_at = now
                row.change_count = F("change_count") + 1
            row.save(update_fields=["answer", "answered_at", "change_count", "flagged"])
        locked.last_seen_at = now
        locked.save(update_fields=["last_seen_at"])
    return {"saved": True, "question_id": question_id, "server_time": now, "deadline_at": locked.deadline_at}


# --- Submit / expiry -------------------------------------------------------------------------------


def submit(attempt, reason):
    """Idempotent: a submitted attempt is never re-submitted or reopened. Grades objective answers."""
    with transaction.atomic():
        locked = Attempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status == Attempt.Status.SUBMITTED:
            attempt.refresh_from_db()
            return attempt
        now = timezone.now()
        locked.status = Attempt.Status.SUBMITTED
        locked.submit_reason = reason
        locked.submitted_at = min(now, locked.deadline_at + grace()) if reason == Attempt.SubmitReason.TIMEOUT else now
        locked.save(update_fields=["status", "submit_reason", "submitted_at"])
        grade_attempt(locked)
    attempt.refresh_from_db()
    return attempt


def expire_if_due(attempt):
    if attempt.is_open and timezone.now() > attempt.deadline_at + grace():
        submit(attempt, Attempt.SubmitReason.TIMEOUT)
        return True
    return False


def sweep_expired(now=None):
    """Auto-submit every attempt whose deadline (plus grace) has passed. Called by cron."""
    now = now or timezone.now()
    due = Attempt.objects.filter(status=Attempt.Status.IN_PROGRESS, deadline_at__lt=now - grace())
    count = 0
    for attempt in due.iterator():
        submit(attempt, Attempt.SubmitReason.TIMEOUT)
        count += 1
    for exam in Exam.objects.filter(status=Exam.Status.SCHEDULED, end_at__lt=now):
        refresh_exam_grading_state(exam)
    return count


# --- Proctoring ------------------------------------------------------------------------------------


def record_event(attempt, event_type, detail=None, client_time=None):
    ProctorEvent.objects.create(
        attempt=attempt, type=event_type, occurred_at=timezone.now(), client_time=client_time, detail=detail or {}
    )
    if event_type not in UNFLAGGED_EVENT_TYPES:
        Attempt.objects.filter(pk=attempt.pk).update(flag_count=F("flag_count") + 1)


def handle_event(request, attempt_id, event_type, detail, client_time):
    """Returns the attempt's live state so the client learns about extensions, termination and auto-submit."""
    attempt = load_attempt(request, attempt_id)
    if attempt.is_open:
        enforce_device(request, attempt)
        if not expire_if_due(attempt):
            if event_type != "heartbeat":
                record_event(attempt, event_type, detail, client_time)
            if event_type == ProctorEvent.Type.FULLSCREEN_EXIT and attempt.exam.setting("require_fullscreen"):
                Attempt.objects.filter(pk=attempt.pk).update(fullscreen_exits=F("fullscreen_exits") + 1)
                attempt.refresh_from_db(fields=["fullscreen_exits"])
                limit = attempt.exam.setting("max_fullscreen_exits") or 0
                if limit and attempt.fullscreen_exits >= limit:
                    submit(attempt, Attempt.SubmitReason.FULLSCREEN_LIMIT)
            if attempt.is_open:
                touch(attempt)
    attempt.refresh_from_db(fields=["status", "submit_reason", "deadline_at", "fullscreen_exits"])
    return {
        "status": attempt.status,
        "submit_reason": attempt.submit_reason,
        "deadline_at": attempt.deadline_at,
        "server_time": timezone.now(),
        "fullscreen_exits": attempt.fullscreen_exits,
    }
