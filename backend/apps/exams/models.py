from decimal import Decimal

from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone

DEFAULT_EXAM_SETTINGS = {
    "shuffle_questions": True,
    "shuffle_options": True,
    "require_fullscreen": True,
    "max_fullscreen_exits": 3,  # 0 = never auto-submit
    "access_code": "",
    "ip_allowlist": [],
    "require_seb": False,
    "seb_config_key": "",
    "show_answers": True,
}
# Classes 1–3: fewer anti-cheat prompts.
SIMPLE_MODE_SETTINGS = {"require_fullscreen": False, "max_fullscreen_exits": 0}


class Question(models.Model):
    class Type(models.TextChoices):
        MCQ_SINGLE = "mcq_single", "MCQ (single answer)"
        MCQ_MULTI = "mcq_multi", "MCQ (multiple answers)"
        TRUE_FALSE = "true_false", "True / False"
        NUMERIC = "numeric", "Numeric"
        SHORT_ANSWER = "short_answer", "Short answer (manual marking)"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    OPTION_TYPES = {Type.MCQ_SINGLE, Type.MCQ_MULTI, Type.TRUE_FALSE}

    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="questions")
    chapter = models.ForeignKey("academics.Chapter", on_delete=models.PROTECT, related_name="questions")
    type = models.CharField(max_length=16, choices=Type.choices)
    text = models.TextField()
    image_key = models.CharField(max_length=255, blank=True)
    difficulty = models.CharField(max_length=8, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("1"))
    negative_marks = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    explanation = models.TextField(blank=True)
    numeric_answer = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    numeric_tolerance = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="versions")
    created_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "questions"
        ordering = ["-id"]
        indexes = [models.Index(fields=["subject", "chapter", "difficulty"])]

    @property
    def has_options(self):
        return self.type in self.OPTION_TYPES

    def is_locked(self):
        """Used in a non-draft exam → edits must create a new version instead of changing history."""
        return self.exam_links.exclude(exam__status=Exam.Status.DRAFT).exists()

    def __str__(self):
        return f"Q{self.pk} v{self.version}: {self.text[:40]}"


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=1000)
    is_correct = models.BooleanField(default=False)  # never serialized to students
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "question_options"
        ordering = ["order", "id"]


class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        GRADED = "graded", "Graded"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=200)
    school_class = models.ForeignKey("academics.SchoolClass", on_delete=models.PROTECT, related_name="exams")
    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="exams")
    instructions = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    duration_min = models.PositiveIntegerField()
    total_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    pass_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    settings = models.JSONField(default=dict, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(django_settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sections = models.ManyToManyField("academics.Section", through="ExamTarget", related_name="exams")

    class Meta:
        db_table = "exams"
        ordering = ["-start_at"]

    def setting(self, key):
        return {**DEFAULT_EXAM_SETTINGS, **(self.settings or {})}.get(key)

    @property
    def effective_settings(self):
        return {**DEFAULT_EXAM_SETTINGS, **(self.settings or {})}

    @property
    def effective_status(self):
        """draft / upcoming / live / closed / graded / published — `live` and `closed` come from the clock."""
        if self.status != self.Status.SCHEDULED:
            return self.status
        now = timezone.now()
        if now < self.start_at:
            return "upcoming"
        if now <= self.end_at:
            return "live"
        return "closed"

    @property
    def is_live(self):
        return self.effective_status == "live"

    @property
    def paper_locked(self):
        return self.status != self.Status.DRAFT

    def __str__(self):
        return self.title


class ExamTarget(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="targets")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "exam_targets"
        constraints = [models.UniqueConstraint(fields=["exam", "section"], name="unique_exam_target")]


class ExamPart(models.Model):
    """A part of the paper (Part A, Part B).

    rule = {"chapters": [ids], "easy": n, "medium": n, "hard": n,
            "marks": {"easy": 1, ...} (optional), "per_student": bool}
    """

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="parts")
    name = models.CharField(max_length=64)
    order = models.PositiveSmallIntegerField(default=0)
    instructions = models.TextField(blank=True)
    rule = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "exam_parts"
        ordering = ["order", "id"]

    @property
    def per_student(self):
        return bool((self.rule or {}).get("per_student"))

    def rule_counts(self):
        rule = self.rule or {}
        return {d: int(rule.get(d) or 0) for d in Question.Difficulty.values}


class ExamQuestion(models.Model):
    """A question on the paper. For per-student parts these rows are the locked pool each attempt draws from."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="exam_questions")
    part = models.ForeignKey(ExamPart, on_delete=models.CASCADE, related_name="exam_questions")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="exam_links")
    order = models.PositiveIntegerField(default=0)
    marks = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        db_table = "exam_questions"
        ordering = ["part__order", "order", "id"]
        constraints = [models.UniqueConstraint(fields=["exam", "question"], name="unique_question_per_exam")]
