import csv
import io
import random
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.academics.models import Chapter, SchoolClass, Subject

from .models import Exam, ExamQuestion, Question, QuestionOption

_rng = random.SystemRandom()


class ExamError(ValueError):
    """A business-rule violation shown to the admin as a 400."""


# --- Question versioning ---------------------------------------------------------------------------


@transaction.atomic
def new_question_version(question, fields, options, user):
    """Edits to a question already used in a scheduled exam create a new version; history keeps the old one.

    Draft exams that reference the old version are moved to the new one.
    """
    old = Question.objects.select_for_update().get(pk=question.pk)
    data = {f.name: getattr(old, f.name) for f in Question._meta.concrete_fields if f.name not in {"id", "created_at"}}
    data.update(fields)
    data.update(version=old.version + 1, parent=old, created_by=user, is_active=True)
    data.pop("parent_id", None)
    data.pop("created_by_id", None)
    new = Question.objects.create(**data)
    source_options = options if options is not None else [
        {"text": o.text, "is_correct": o.is_correct, "order": o.order} for o in old.options.all()
    ]
    QuestionOption.objects.bulk_create([QuestionOption(question=new, **o) for o in source_options])
    old.is_active = False
    old.save(update_fields=["is_active"])
    ExamQuestion.objects.filter(question=old, exam__status=Exam.Status.DRAFT).update(question=new)
    return new


# --- Generator -------------------------------------------------------------------------------------


def _eligible(exam, part, exclude_ids):
    rule = part.rule or {}
    qs = Question.objects.filter(subject=exam.subject, is_active=True).exclude(pk__in=exclude_ids)
    if rule.get("chapters"):
        qs = qs.filter(chapter_id__in=rule["chapters"])
    return qs


def _marks_for(part, question):
    per_difficulty = (part.rule or {}).get("marks") or {}
    if question.difficulty in per_difficulty:
        return Decimal(str(per_difficulty[question.difficulty]))
    return question.marks


@transaction.atomic
def generate_part(exam, part):
    """Fill one part from its rule.

    Fixed parts pick the questions now. Per-student parts store the whole eligible pool; each attempt draws
    its own set from that pool at start, so every student gets a different paper from the same rule.
    """
    if exam.paper_locked:
        raise ExamError("The paper is locked once the exam is scheduled.")
    counts = part.rule_counts()
    if not any(counts.values()):
        raise ExamError(f"{part.name}: the rule asks for no questions.")
    ExamQuestion.objects.filter(part=part).delete()
    used = set(ExamQuestion.objects.filter(exam=exam).values_list("question_id", flat=True))
    by_difficulty = defaultdict(list)
    for q in _eligible(exam, part, used):
        by_difficulty[q.difficulty].append(q)

    shortfalls = [
        f"{n} {d} needed, {len(by_difficulty[d])} available" for d, n in counts.items() if n > len(by_difficulty[d])
    ]
    if shortfalls:
        raise ExamError(f"{part.name}: not enough questions in the bank ({'; '.join(shortfalls)}).")

    chosen = []
    for difficulty, n in counts.items():
        if n == 0:
            continue
        pool = by_difficulty[difficulty]
        chosen.extend(pool if part.per_student else _rng.sample(pool, n))
    rows = [
        ExamQuestion(exam=exam, part=part, question=q, order=i, marks=_marks_for(part, q)) for i, q in enumerate(chosen)
    ]
    ExamQuestion.objects.bulk_create(rows)
    return len(rows)


def generate(exam, part=None):
    parts = [part] if part else [p for p in exam.parts.all() if p.rule_counts() and any(p.rule_counts().values())]
    if not parts:
        raise ExamError("No part has a rule to generate from.")
    return {p.name: generate_part(exam, p) for p in parts}


# --- Scheduling ------------------------------------------------------------------------------------


def paper_total(exam):
    """Total marks every student will face. Per-student parts must have equal marks within each difficulty."""
    total = Decimal("0")
    for part in exam.parts.prefetch_related("exam_questions__question"):
        eqs = list(part.exam_questions.all())
        if not eqs:
            raise ExamError(f"{part.name} has no questions.")
        if not part.per_student:
            total += sum((eq.marks for eq in eqs), Decimal("0"))
            continue
        marks_by_difficulty = defaultdict(set)
        count_by_difficulty = defaultdict(int)
        for eq in eqs:
            marks_by_difficulty[eq.question.difficulty].add(eq.marks)
            count_by_difficulty[eq.question.difficulty] += 1
        for difficulty, n in part.rule_counts().items():
            if n == 0:
                continue
            if count_by_difficulty[difficulty] < n:
                raise ExamError(f"{part.name}: pool has fewer {difficulty} questions than the rule needs.")
            if len(marks_by_difficulty[difficulty]) != 1:
                raise ExamError(
                    f"{part.name}: per-student sets need equal marks for all {difficulty} questions "
                    "(set rule.marks or align question marks)."
                )
            total += n * next(iter(marks_by_difficulty[difficulty]))
    return total


@transaction.atomic
def schedule(exam):
    exam = Exam.objects.select_for_update().get(pk=exam.pk)
    if exam.status != Exam.Status.DRAFT:
        raise ExamError("Only a draft exam can be scheduled.")
    if exam.end_at <= exam.start_at:
        raise ExamError("End time must be after start time.")
    if exam.end_at <= timezone.now():
        raise ExamError("The exam window has already ended.")
    targets = list(exam.targets.select_related("section"))
    if not targets:
        raise ExamError("Choose at least one target section.")
    if any(t.section.school_class_id != exam.school_class_id for t in targets):
        raise ExamError("All target sections must belong to the exam's class.")
    if not exam.parts.exists():
        raise ExamError("Add at least one part with questions.")
    total = paper_total(exam)
    if total <= 0:
        raise ExamError("The paper has no marks.")
    if exam.pass_marks > total:
        raise ExamError(f"Pass marks ({exam.pass_marks}) exceed total marks ({total}).")
    exam.total_marks = total
    exam.status = Exam.Status.SCHEDULED
    exam.scheduled_at = timezone.now()
    exam.save(update_fields=["total_marks", "status", "scheduled_at", "updated_at"])
    return exam


@transaction.atomic
def unschedule(exam):
    exam = Exam.objects.select_for_update().get(pk=exam.pk)
    if exam.status != Exam.Status.SCHEDULED:
        raise ExamError("Only a scheduled exam can be moved back to draft.")
    if exam.attempts.exists():
        raise ExamError("Students have already started this exam; it cannot go back to draft.")
    exam.status = Exam.Status.DRAFT
    exam.scheduled_at = None
    exam.save(update_fields=["status", "scheduled_at", "updated_at"])
    return exam


# --- Question CSV import ---------------------------------------------------------------------------

IMPORT_COLUMNS = ["class", "subject", "chapter", "type", "difficulty", "text", "marks", "options", "correct"]
MAX_IMPORT_ROWS = 2000


def _decimal(value, default=None):
    value = (value or "").strip()
    if not value:
        return default
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"'{value}' is not a number") from None


def _correct_indices(value, n_options):
    """'B' / '2' / 'A|C' / '1|3' → zero-based indices."""
    picks = []
    for token in (value or "").replace(",", "|").split("|"):
        token = token.strip().upper()
        if not token:
            continue
        if token.isdigit():
            idx = int(token) - 1
        elif len(token) == 1 and token.isalpha():
            idx = ord(token) - ord("A")
        else:
            raise ValueError(f"cannot read correct answer '{token}'")
        if not 0 <= idx < n_options:
            raise ValueError(f"correct answer '{token}' is not one of the options")
        picks.append(idx)
    return sorted(set(picks))


def import_questions(uploaded, user):
    """CSV columns: class, subject, chapter, type, difficulty, text, marks, options, correct
    (+ optional negative_marks, explanation, tolerance). Options are separated by '|'. For numeric questions
    `correct` is the value. Chapters are created if missing; subjects must already exist. All-or-nothing."""
    raw = uploaded.read()
    if len(raw) > 2 * 1024 * 1024:
        raise ExamError("File is larger than 2 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExamError("File must be UTF-8 encoded CSV.") from None
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in IMPORT_COLUMNS if c not in headers]
    if missing:
        raise ExamError(f"Missing columns: {', '.join(missing)}")
    reader.fieldnames = headers
    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise ExamError(f"At most {MAX_IMPORT_ROWS} rows per import.")

    classes = {c.grade: c for c in SchoolClass.objects.all()}
    subjects = {(s.school_class.grade, s.name.lower()): s for s in Subject.objects.select_related("school_class")}
    types, difficulties = set(Question.Type.values), set(Question.Difficulty.values)
    errors, parsed = [], []
    for line, row in enumerate(rows, start=2):
        try:
            grade = int((row.get("class") or "").strip())
            if grade not in classes:
                raise ValueError("unknown class")
            subject = subjects.get((grade, (row.get("subject") or "").strip().lower()))
            if subject is None:
                raise ValueError("unknown subject for that class")
            chapter_name = (row.get("chapter") or "").strip()
            if not chapter_name:
                raise ValueError("chapter is required")
            qtype = (row.get("type") or "").strip().lower()
            if qtype not in types:
                raise ValueError(f"type must be one of {', '.join(sorted(types))}")
            difficulty = (row.get("difficulty") or "medium").strip().lower()
            if difficulty not in difficulties:
                raise ValueError("difficulty must be easy, medium or hard")
            qtext = (row.get("text") or "").strip()
            if not qtext:
                raise ValueError("text is required")
            marks = _decimal(row.get("marks"), Decimal("1"))
            negative = _decimal(row.get("negative_marks"), Decimal("0"))
            if marks <= 0 or negative < 0:
                raise ValueError("marks must be > 0 and negative_marks ≥ 0")
            item = {
                "subject": subject,
                "chapter_name": chapter_name,
                "fields": {
                    "type": qtype,
                    "difficulty": difficulty,
                    "text": qtext,
                    "marks": marks,
                    "negative_marks": negative,
                    "explanation": (row.get("explanation") or "").strip(),
                },
                "options": [],
            }
            if qtype in Question.OPTION_TYPES:
                options = [o.strip() for o in (row.get("options") or "").split("|") if o.strip()]
                if qtype == Question.Type.TRUE_FALSE and not options:
                    options = ["True", "False"]
                if len(options) < 2:
                    raise ValueError("at least two options are required")
                correct = _correct_indices(row.get("correct"), len(options))
                if not correct:
                    raise ValueError("mark at least one correct option")
                if qtype != Question.Type.MCQ_MULTI and len(correct) != 1:
                    raise ValueError("exactly one correct option is required")
                item["options"] = [
                    {"text": t, "is_correct": i in correct, "order": i} for i, t in enumerate(options)
                ]
            elif qtype == Question.Type.NUMERIC:
                value = _decimal(row.get("correct"))
                if value is None:
                    raise ValueError("numeric questions need the correct value")
                item["fields"]["numeric_answer"] = value
                item["fields"]["numeric_tolerance"] = _decimal(row.get("tolerance"), Decimal("0"))
            parsed.append(item)
        except ValueError as exc:
            errors.append({"row": line, "error": str(exc)})
    if errors:
        raise ExamError({"detail": "No questions were imported.", "errors": errors})

    created = 0
    with transaction.atomic():
        chapters = {}
        for item in parsed:
            key = (item["subject"].pk, item["chapter_name"].lower())
            if key not in chapters:
                chapter = Chapter.objects.filter(subject=item["subject"], name__iexact=item["chapter_name"]).first()
                if chapter is None:
                    next_order = item["subject"].chapters.count() + 1
                    chapter = Chapter.objects.create(subject=item["subject"], name=item["chapter_name"], order=next_order)
                chapters[key] = chapter
            q = Question.objects.create(subject=item["subject"], chapter=chapters[key], created_by=user, **item["fields"])
            QuestionOption.objects.bulk_create([QuestionOption(question=q, **o) for o in item["options"]])
            created += 1
    return created

