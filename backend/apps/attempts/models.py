from django.conf import settings
from django.db import models


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"

    class SubmitReason(models.TextChoices):
        STUDENT = "student", "Submitted by student"
        TIMEOUT = "timeout", "Time ran out"
        FULLSCREEN_LIMIT = "fullscreen_limit", "Too many full-screen exits"
        ADMIN = "admin", "Ended by admin"

    class Grading(models.TextChoices):
        PENDING = "pending", "Not graded"
        PENDING_MANUAL = "pending_manual", "Awaiting manual marking"
        GRADED = "graded", "Graded"

    exam = models.ForeignKey("exams.Exam", on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attempts")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    submit_reason = models.CharField(max_length=20, choices=SubmitReason.choices, blank=True)
    started_at = models.DateTimeField()
    deadline_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    # [{"q": question_id, "part": part_id, "marks": "2.00", "opts": [[token, option_id], ...]}, ...]
    question_order = models.JSONField(default=list)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    grading_status = models.CharField(max_length=16, choices=Grading.choices, default=Grading.PENDING)
    rank = models.PositiveIntegerField(null=True, blank=True)
    flag_count = models.PositiveIntegerField(default=0)
    fullscreen_exits = models.PositiveIntegerField(default=0)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "attempts"
        constraints = [models.UniqueConstraint(fields=["exam", "student"], name="one_attempt_per_student")]
        indexes = [models.Index(fields=["exam", "status"]), models.Index(fields=["status", "deadline_at"])]

    @property
    def is_open(self):
        return self.status == self.Status.IN_PROGRESS

    def entry(self, question_id):
        for item in self.question_order:
            if item["q"] == question_id:
                return item
        return None

    def __str__(self):
        return f"Attempt {self.pk} exam={self.exam_id} student={self.student_id}"


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("exams.Question", on_delete=models.PROTECT, related_name="+")
    # {"options": [option_id, ...]} | {"value": "12.5"} | {"text": "..."}; option ids, never tokens
    answer = models.JSONField(default=dict)
    flagged = models.BooleanField(default=False)  # "mark for review"
    is_correct = models.BooleanField(null=True, blank=True)
    marks_awarded = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    answered_at = models.DateTimeField()
    change_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "attempt_answers"
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")]
        indexes = [models.Index(fields=["attempt"])]


class ProctorEvent(models.Model):
    """Browser-reported and server-detected integrity events. They are evidence for review, not proof."""

    class Type(models.TextChoices):
        TAB_SWITCH = "tab_switch", "Tab switch"
        BLUR = "blur", "Window lost focus"
        FULLSCREEN_EXIT = "fullscreen_exit", "Left full screen"
        PASTE = "paste", "Paste attempt"
        COPY = "copy", "Copy attempt"
        CONTEXT_MENU = "context_menu", "Right-click"
        PRINT = "print", "Print attempt"
        OFFLINE = "offline", "Went offline"
        SECOND_LOGIN = "second_login", "Second device"
        IP_CHANGE = "ip_change", "IP address changed"
        LATE_ANSWER = "late_answer", "Answer after deadline"

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=20, choices=Type.choices)
    occurred_at = models.DateTimeField()
    client_time = models.DateTimeField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "proctor_events"
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["attempt"])]


CLIENT_EVENT_TYPES = {
    ProctorEvent.Type.TAB_SWITCH,
    ProctorEvent.Type.BLUR,
    ProctorEvent.Type.FULLSCREEN_EXIT,
    ProctorEvent.Type.PASTE,
    ProctorEvent.Type.COPY,
    ProctorEvent.Type.CONTEXT_MENU,
    ProctorEvent.Type.PRINT,
    ProctorEvent.Type.OFFLINE,
}
UNFLAGGED_EVENT_TYPES = {ProctorEvent.Type.OFFLINE}
