"""Server-side grading. Runs on submit, on sweep, and on admin re-grade; never in the browser."""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.exams.models import Exam, Question

from .models import Attempt

ZERO = Decimal("0")


def _numeric(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def grade_answer(question, marks, answer):
    """Return (is_correct, marks_awarded) for one answer. (None, None) means manual marking is needed."""
    marks = Decimal(str(marks))
    negative = question.negative_marks or ZERO
    qtype = question.type

    if qtype == Question.Type.SHORT_ANSWER:
        return None, None

    if qtype in Question.OPTION_TYPES:
        chosen = set(answer.get("options") or [])
        if not chosen:
            return None, ZERO  # blank: no marks, no penalty
        correct = {o.id for o in question.options.all() if o.is_correct}
        if qtype in {Question.Type.MCQ_SINGLE, Question.Type.TRUE_FALSE} and len(chosen) != 1:
            return False, -negative
        return (True, marks) if chosen == correct else (False, -negative)

    if qtype == Question.Type.NUMERIC:
        raw = answer.get("value")
        if raw in (None, ""):
            return None, ZERO
        value = _numeric(raw)
        if value is None or question.numeric_answer is None:
            return False, -negative
        ok = abs(value - question.numeric_answer) <= (question.numeric_tolerance or ZERO)
        return (True, marks) if ok else (False, -negative)

    return None, ZERO


def _questions_for(attempt):
    ids = [item["q"] for item in attempt.question_order]
    return {q.pk: q for q in Question.objects.filter(pk__in=ids).prefetch_related("options")}


@transaction.atomic
def grade_attempt(attempt, questions=None, keep_manual=True):
    """(Re)grade every answer of a submitted attempt and store the score.

    Short answers already marked by a teacher keep their marks when `keep_manual` is set.
    """
    questions = questions or _questions_for(attempt)
    marks_by_q = {item["q"]: Decimal(str(item["marks"])) for item in attempt.question_order}
    answers = {a.question_id: a for a in attempt.answers.select_for_update()}
    pending_manual = False
    total = ZERO
    for qid, marks in marks_by_q.items():
        question = questions[qid]
        answer = answers.get(qid)
        if answer is None:
            continue
        if question.type == Question.Type.SHORT_ANSWER:
            has_text = bool((answer.answer.get("text") or "").strip())
            if not has_text:
                answer.is_correct, answer.marks_awarded = None, ZERO
            elif not (keep_manual and answer.marked_by_id):
                answer.is_correct, answer.marks_awarded = None, None
                pending_manual = True
        else:
            answer.is_correct, answer.marks_awarded = grade_answer(question, marks, answer.answer)
        answer.save(update_fields=["is_correct", "marks_awarded"])
        if answer.marks_awarded is not None:
            total += answer.marks_awarded

    attempt.max_score = sum(marks_by_q.values(), ZERO)
    attempt.score = total
    attempt.grading_status = Attempt.Grading.PENDING_MANUAL if pending_manual else Attempt.Grading.GRADED
    attempt.save(update_fields=["score", "max_score", "grading_status"])
    return attempt


def recompute_score(attempt):
    """After manual marking: total up stored marks and settle grading status."""
    answers = list(attempt.answers.select_related("question"))
    pending = any(
        a.question.type == Question.Type.SHORT_ANSWER and a.marks_awarded is None for a in answers
    )
    attempt.score = sum((a.marks_awarded or ZERO for a in answers), ZERO)
    attempt.grading_status = Attempt.Grading.PENDING_MANUAL if pending else Attempt.Grading.GRADED
    attempt.save(update_fields=["score", "grading_status"])
    return attempt


def regrade_exam(exam):
    """Re-grade all submitted attempts (after an answer-key fix). Returns the number re-graded."""
    attempts = list(exam.attempts.filter(status=Attempt.Status.SUBMITTED))
    ids = {item["q"] for a in attempts for item in a.question_order}
    questions = {q.pk: q for q in Question.objects.filter(pk__in=ids).prefetch_related("options")}
    for attempt in attempts:
        grade_attempt(attempt, questions)
    refresh_exam_grading_state(exam)
    return len(attempts)


def refresh_exam_grading_state(exam):
    """Scheduled → Graded once the window is over and every attempt is submitted and fully marked."""
    exam.refresh_from_db(fields=["status", "end_at"])
    if exam.status != Exam.Status.SCHEDULED or exam.effective_status != "closed":
        return exam
    not_done = exam.attempts.exclude(status=Attempt.Status.SUBMITTED, grading_status=Attempt.Grading.GRADED)
    if not not_done.exists():
        exam.status = Exam.Status.GRADED
        exam.save(update_fields=["status", "updated_at"])
    return exam
