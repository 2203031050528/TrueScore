from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone

from apps.academics.models import Chapter
from apps.accounts.models import StudentProfile
from apps.attempts.grading import refresh_exam_grading_state, regrade_exam
from apps.attempts.models import Attempt, AttemptAnswer
from apps.attempts.services import exams_for_student, sweep_expired
from apps.core.storage import get_storage
from apps.exams.models import Exam, Question
from apps.videos.models import Video, WatchProgress

from .models import ResultPublication

ZERO = Decimal("0")


class ResultError(ValueError):
    pass


def pct(score, max_score):
    if not max_score:
        return 0.0
    return round(float(score or 0) * 100 / float(max_score), 2)


# --- Review -------------------------------------------------------------------------------------


def answer_review(attempt, reveal):
    """Per-question review in the student's own order. `reveal` adds the key and explanation."""
    ids = [item["q"] for item in attempt.question_order]
    questions = {q.pk: q for q in Question.objects.filter(pk__in=ids).prefetch_related("options")}
    answers = {a.question_id: a for a in attempt.answers.all()}
    parts = {p.pk: p.name for p in attempt.exam.parts.all()}
    storage = get_storage()
    out = []
    for number, item in enumerate(attempt.question_order, start=1):
        q = questions[item["q"]]
        a = answers.get(q.pk)
        chosen = set((a.answer.get("options") if a else None) or [])
        by_id = {o.pk: o for o in q.options.all()}
        options = []
        for _token, opt_id in item["opts"]:
            opt = by_id.get(opt_id)
            if opt is None:
                continue
            row = {"text": opt.text, "chosen": opt_id in chosen}
            if reveal:
                row["is_correct"] = opt.is_correct
            options.append(row)
        entry = {
            "number": number,
            "question_id": q.pk,
            "part": parts.get(item["part"], ""),
            "type": q.type,
            "text": q.text,
            "image_url": storage.download_url(q.image_key, 900) if q.image_key else None,
            "marks": item["marks"],
            "options": options,
            "your_answer": None if a is None else {k: v for k, v in a.answer.items() if k != "options"},
            "answered": a is not None and bool(chosen or (a.answer.get("value") or a.answer.get("text") or "").strip()),
            "is_correct": a.is_correct if a else None,
            "marks_awarded": a.marks_awarded if a else ZERO,
        }
        if reveal:
            entry["explanation"] = q.explanation
            if q.type == Question.Type.NUMERIC:
                entry["correct_value"] = q.numeric_answer
                entry["tolerance"] = q.numeric_tolerance
        out.append(entry)
    return out


# --- Ranks & publishing --------------------------------------------------------------------------


def compute_section_ranks(exam, section_id):
    """Standard competition ranking (1, 2, 2, 4) by score within one section."""
    attempts = list(
        Attempt.objects.filter(exam=exam, section_id=section_id, status=Attempt.Status.SUBMITTED).order_by("-score", "submitted_at")
    )
    previous_score, previous_rank = None, 0
    for index, attempt in enumerate(attempts, start=1):
        rank = previous_rank if attempt.score == previous_score else index
        if attempt.rank != rank:
            attempt.rank = rank
            attempt.save(update_fields=["rank"])
        previous_score, previous_rank = attempt.score, rank
    return len(attempts)


def recompute_ranks_if_published(exam):
    for section_id in exam.publications.values_list("section_id", flat=True):
        compute_section_ranks(exam, section_id)


@transaction.atomic
def publish(exam, section_ids, show_answers, user):
    exam = Exam.objects.select_for_update().get(pk=exam.pk)
    if exam.status == Exam.Status.DRAFT:
        raise ResultError("A draft exam has no results.")
    if exam.status == Exam.Status.SCHEDULED and exam.effective_status != "closed":
        raise ResultError("Results can be published only after the exam window has closed.")
    targets = set(exam.targets.values_list("section_id", flat=True))
    chosen = set(section_ids or targets)
    if not chosen <= targets:
        raise ResultError("Some sections are not targets of this exam.")

    sweep_expired()
    attempts = Attempt.objects.filter(exam=exam, section_id__in=chosen)
    if attempts.filter(status=Attempt.Status.IN_PROGRESS).exists():
        raise ResultError("Some students are still writing (their time was extended). Wait or end those attempts.")
    if attempts.filter(grading_status=Attempt.Grading.PENDING_MANUAL).exists():
        raise ResultError("Some short answers still need marking.")

    published = []
    for section_id in sorted(chosen):
        compute_section_ranks(exam, section_id)
        ResultPublication.objects.update_or_create(
            exam=exam, section_id=section_id, defaults={"published_by": user, "show_answers": show_answers}
        )
        published.append(section_id)

    refresh_exam_grading_state(exam)
    if set(exam.publications.values_list("section_id", flat=True)) >= targets:
        exam.status = Exam.Status.PUBLISHED
        exam.published_at = timezone.now()
        exam.save(update_fields=["status", "published_at", "updated_at"])
    return published


@transaction.atomic
def unpublish(exam, section_ids):
    qs = exam.publications.all()
    if section_ids:
        qs = qs.filter(section_id__in=section_ids)
    removed = list(qs.values_list("section_id", flat=True))
    qs.delete()
    if exam.status == Exam.Status.PUBLISHED:
        exam.status = Exam.Status.GRADED
        exam.published_at = None
        exam.save(update_fields=["status", "published_at", "updated_at"])
    return removed


# --- Re-grade --------------------------------------------------------------------------------------


@transaction.atomic
def fix_key_and_regrade(exam, question_id, correct_option_ids=None, numeric_answer=None, numeric_tolerance=None):
    """The one audited way to change grading after the paper is locked."""
    before, after = None, None
    if question_id is not None:
        if not exam.exam_questions.filter(question_id=question_id).exists():
            raise ResultError("That question is not on this paper.")
        q = Question.objects.select_for_update().prefetch_related("options").get(pk=question_id)
        if q.has_options:
            if not correct_option_ids:
                raise ResultError("Give the corrected option ids.")
            valid = {o.pk for o in q.options.all()}
            chosen = set(correct_option_ids)
            if not chosen <= valid:
                raise ResultError("Some options do not belong to this question.")
            if q.type != Question.Type.MCQ_MULTI and len(chosen) != 1:
                raise ResultError("Exactly one option must be correct for this question type.")
            before = {"correct_option_ids": sorted(o.pk for o in q.options.all() if o.is_correct)}
            q.options.update(is_correct=False)
            q.options.filter(pk__in=chosen).update(is_correct=True)
            after = {"correct_option_ids": sorted(chosen)}
        elif q.type == Question.Type.NUMERIC:
            if numeric_answer is None:
                raise ResultError("Give the corrected numeric answer.")
            before = {"numeric_answer": q.numeric_answer, "numeric_tolerance": q.numeric_tolerance}
            q.numeric_answer = numeric_answer
            if numeric_tolerance is not None:
                q.numeric_tolerance = numeric_tolerance
            q.save(update_fields=["numeric_answer", "numeric_tolerance"])
            after = {"numeric_answer": q.numeric_answer, "numeric_tolerance": q.numeric_tolerance}
        else:
            raise ResultError("Short answers are marked by hand, not by key.")
    count = regrade_exam(exam)
    recompute_ranks_if_published(exam)
    return {"regraded_attempts": count, "before": before, "after": after}


# --- Analytics -------------------------------------------------------------------------------------


def analytics(exam):
    attempts = list(Attempt.objects.filter(exam=exam).select_related("section__school_class"))
    submitted = [a for a in attempts if a.status == Attempt.Status.SUBMITTED and a.score is not None]
    scores = [a.score for a in submitted]
    targets = list(exam.targets.select_related("section__school_class"))
    target_ids = [t.section_id for t in targets]
    enrolled = StudentProfile.objects.filter(section_id__in=target_ids, user__is_active=True).count()
    passed = [a for a in submitted if a.score >= exam.pass_marks]

    distribution = [0] * 10
    for a in submitted:
        bucket = min(9, max(0, int(pct(a.score, a.max_score) // 10)))
        distribution[bucket] += 1

    served = defaultdict(int)
    marks_available = defaultdict(lambda: ZERO)
    for a in submitted:
        for item in a.question_order:
            served[item["q"]] += 1
            marks_available[item["q"]] += Decimal(str(item["marks"]))
    stats = defaultdict(lambda: {"answered": 0, "correct": 0, "marks": ZERO})
    for row in AttemptAnswer.objects.filter(attempt__in=submitted).values("question_id", "is_correct", "marks_awarded"):
        s = stats[row["question_id"]]
        s["answered"] += 1
        s["correct"] += 1 if row["is_correct"] else 0
        s["marks"] += row["marks_awarded"] or ZERO
    questions = {q.pk: q for q in Question.objects.filter(pk__in=served.keys()).select_related("chapter")}
    per_question = []
    for qid, n in served.items():
        q = questions[qid]
        s = stats[qid]
        per_question.append(
            {
                "question_id": qid,
                "text": q.text[:160],
                "type": q.type,
                "difficulty": q.difficulty,
                "chapter": q.chapter.name,
                "served": n,
                "answered": s["answered"],
                "correct": s["correct"],
                "accuracy": round(100 * s["correct"] / n, 1) if n else 0,
                "avg_marks_pct": pct(s["marks"], marks_available[qid]),
            }
        )
    per_question.sort(key=lambda r: r["accuracy"])

    published = set(exam.publications.values_list("section_id", flat=True))
    per_section = []
    for t in targets:
        sec = [a for a in submitted if a.section_id == t.section_id]
        per_section.append(
            {
                "section_id": t.section_id,
                "section": t.section.label,
                "submitted": len(sec),
                "average": round(float(sum((a.score for a in sec), ZERO)) / len(sec), 2) if sec else None,
                "pass_rate": round(100 * sum(1 for a in sec if a.score >= exam.pass_marks) / len(sec), 1) if sec else None,
                "published": t.section_id in published,
            }
        )

    return {
        "exam": {
            "id": exam.pk,
            "title": exam.title,
            "status": exam.effective_status,
            "total_marks": exam.total_marks,
            "pass_marks": exam.pass_marks,
        },
        "enrolled": enrolled,
        "started": len(attempts),
        "submitted": len(submitted),
        "in_progress": sum(1 for a in attempts if a.status == Attempt.Status.IN_PROGRESS),
        "pending_manual": sum(1 for a in attempts if a.grading_status == Attempt.Grading.PENDING_MANUAL),
        "average": round(float(sum(scores, ZERO)) / len(scores), 2) if scores else None,
        "highest": max(scores) if scores else None,
        "lowest": min(scores) if scores else None,
        "pass_rate": round(100 * len(passed) / len(submitted), 1) if submitted else None,
        "distribution": [{"range": f"{i * 10}-{i * 10 + 10}%", "count": c} for i, c in enumerate(distribution)],
        "per_question": per_question,
        "per_section": per_section,
    }


# --- Student-facing ------------------------------------------------------------------------------


def published_attempts(user):
    """Only attempts whose (exam, section) has a publication row are ever shown with scores."""
    return (
        Attempt.objects.filter(
            student=user,
            status=Attempt.Status.SUBMITTED,
            exam__publications__section_id=F("section_id"),
        )
        .select_related("exam__subject")
        .distinct()
    )


def result_summary(attempt, publication, section_size):
    exam = attempt.exam
    return {
        "exam_id": exam.pk,
        "title": exam.title,
        "subject": exam.subject.name,
        "date": exam.start_at,
        "score": attempt.score,
        "max_score": attempt.max_score,
        "percentage": pct(attempt.score, attempt.max_score),
        "passed": attempt.score is not None and attempt.score >= exam.pass_marks,
        "pass_marks": exam.pass_marks,
        "rank": attempt.rank,
        "section_size": section_size,
        "published_at": publication.published_at,
        "show_answers": publication.show_answers and bool(exam.setting("show_answers")),
    }


def section_sizes(attempts):
    keys = {(a.exam_id, a.section_id) for a in attempts}
    if not keys:
        return {}
    rows = (
        Attempt.objects.filter(exam_id__in={k[0] for k in keys}, status=Attempt.Status.SUBMITTED)
        .values("exam_id", "section_id")
        .annotate(n=Count("id"))
    )
    return {(r["exam_id"], r["section_id"]): r["n"] for r in rows}


def progress_dashboard(user):
    profile = user.student_profile
    now = timezone.now()

    # Video completion per subject.
    videos = list(
        Video.objects.filter(status=Video.Status.PUBLISHED, chapter__subject__school_class_id=profile.school_class_id).select_related("chapter__subject")
    )
    progress = {p.video_id: p for p in WatchProgress.objects.filter(student=user, video__in=videos)}
    subjects = {}
    for v in videos:
        s = subjects.setdefault(v.chapter.subject_id, {"subject_id": v.chapter.subject_id, "subject": v.chapter.subject.name, "videos": 0, "completed": 0})
        s["videos"] += 1
        if progress.get(v.pk) and progress[v.pk].completed_at:
            s["completed"] += 1
    for s in subjects.values():
        s["percent"] = round(100 * s["completed"] / s["videos"]) if s["videos"] else 0

    continue_watching = [
        {
            "video_id": p.video_id,
            "title": p.video.title,
            "subject": p.video.chapter.subject.name,
            "last_position_s": p.last_position_s,
            "duration_s": p.video.duration_s,
        }
        for p in WatchProgress.objects.filter(student=user, completed_at__isnull=True, last_position_s__gt=0, video__status=Video.Status.PUBLISHED, video__chapter__subject__school_class_id=profile.school_class_id)
        .select_related("video__chapter__subject")
        .order_by("-updated_at")[:4]
    ]

    upcoming = [
        {"id": e.pk, "title": e.title, "subject": e.subject.name, "start_at": e.start_at, "end_at": e.end_at, "status": e.effective_status}
        for e in exams_for_student(user).filter(status=Exam.Status.SCHEDULED, end_at__gte=now).exclude(attempts__student=user).order_by("start_at")[:5]
    ]

    attempts = list(published_attempts(user).order_by("exam__start_at"))
    pubs = {(p.exam_id, p.section_id): p for p in ResultPublication.objects.filter(exam__in=[a.exam_id for a in attempts])}
    sizes = section_sizes(attempts)
    results = [result_summary(a, pubs[(a.exam_id, a.section_id)], sizes.get((a.exam_id, a.section_id), 0)) for a in attempts]
    trend = [{"exam_id": r["exam_id"], "title": r["title"], "date": r["date"], "percentage": r["percentage"]} for r in results]

    # Weakest chapters: share of available marks earned, across published exams (unanswered = 0).
    chapter_totals = defaultdict(lambda: [ZERO, ZERO])
    qids = {item["q"] for a in attempts for item in a.question_order}
    chapter_of = dict(Question.objects.filter(pk__in=qids).values_list("pk", "chapter_id"))
    chapter_names = dict(Chapter.objects.filter(pk__in=set(chapter_of.values())).values_list("pk", "name"))
    for a in attempts:
        awarded = {ans.question_id: ans.marks_awarded or ZERO for ans in a.answers.all()}
        for item in a.question_order:
            ch = chapter_of.get(item["q"])
            chapter_totals[ch][0] += max(ZERO, awarded.get(item["q"], ZERO))
            chapter_totals[ch][1] += Decimal(str(item["marks"]))
    weak = sorted(
        (
            {"chapter_id": ch, "chapter": chapter_names.get(ch, ""), "percentage": pct(got, avail)}
            for ch, (got, avail) in chapter_totals.items()
            if avail > 0
        ),
        key=lambda r: r["percentage"],
    )[:3]

    latest = results[-1] if results else None
    return {
        "student": {"name": user.full_name, "roll_no": profile.roll_no, "section": profile.section.label, "grade": profile.school_class.grade},
        "subjects": sorted(subjects.values(), key=lambda s: s["subject"]),
        "continue_watching": continue_watching,
        "upcoming_exams": upcoming,
        "latest_results": list(reversed(results[-5:])),
        "score_trend": trend,
        "weak_chapters": weak,
        "rank": {"exam": latest["title"], "rank": latest["rank"], "section_size": latest["section_size"]} if latest else None,
    }
