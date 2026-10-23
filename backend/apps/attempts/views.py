from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import connection
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StudentProfile
from apps.audit.services import audit
from apps.core.permissions import InternalSecret, IsAdmin, IsStudent
from apps.core.throttles import AdminThrottle, AnswerThrottle, EventThrottle, InternalThrottle
from apps.exams.models import Exam, Question

from . import services
from .grading import recompute_score, refresh_exam_grading_state
from .models import CLIENT_EVENT_TYPES, Attempt, AttemptAnswer


def _error(exc):
    return Response(exc.payload(), status=exc.status)


# --- Student -------------------------------------------------------------------------------------


class UpcomingExamsView(APIView):
    """Scheduled and live exams for the student's own section, with their attempt status."""

    permission_classes = [IsStudent]

    def get(self, request):
        now = timezone.now()
        exams = services.exams_for_student(request.user).filter(end_at__gte=now - timedelta(days=30)).order_by("start_at")
        attempts = {a.exam_id: a for a in Attempt.objects.filter(student=request.user, exam__in=exams)}
        out = []
        for exam in exams:
            attempt = attempts.get(exam.pk)
            out.append(
                {
                    "id": exam.pk,
                    "title": exam.title,
                    "subject": exam.subject.name,
                    "start_at": exam.start_at,
                    "end_at": exam.end_at,
                    "duration_min": exam.duration_min,
                    "total_marks": str(exam.total_marks),
                    "status": exam.effective_status,
                    "needs_access_code": bool((exam.setting("access_code") or "").strip()),
                    "require_fullscreen": exam.setting("require_fullscreen"),
                    "instructions": exam.instructions,
                    "attempt": None
                    if attempt is None
                    else {"id": attempt.pk, "status": attempt.status, "submitted_at": attempt.submitted_at},
                }
            )
        return Response({"server_time": now, "results": out})


class StartAttemptView(APIView):
    permission_classes = [IsStudent]
    throttle_classes = [AnswerThrottle]

    def post(self, request, exam_id):
        try:
            attempt, created = services.start_attempt(request, exam_id)
        except services.AttemptError as exc:
            return _error(exc)
        attempt = Attempt.objects.select_related("exam__subject", "student__student_profile__school_class").get(pk=attempt.pk)
        return Response(services.attempt_state(attempt), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AttemptDetailView(APIView):
    """Resume after a disconnect — same device only."""

    permission_classes = [IsStudent]

    def get(self, request, attempt_id):
        try:
            attempt = services.load_attempt(request, attempt_id)
            services.resume(request, attempt)
        except services.AttemptError as exc:
            return _error(exc)
        attempt.refresh_from_db()
        return Response(services.attempt_state(attempt))


class AnswerSerializer(serializers.Serializer):
    options = serializers.ListField(child=serializers.CharField(max_length=16), required=False, max_length=8)
    value = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    text = serializers.CharField(max_length=services.MAX_SHORT_ANSWER, required=False, allow_blank=True, trim_whitespace=False)
    flagged = serializers.BooleanField(required=False, default=False)


class SaveAnswerView(APIView):
    permission_classes = [IsStudent]
    throttle_classes = [AnswerThrottle]

    def put(self, request, attempt_id, question_id):
        s = AnswerSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = services.save_answer(request, attempt_id, question_id, s.validated_data)
        except services.AttemptError as exc:
            return _error(exc)
        return Response(result)


class EventSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=sorted(CLIENT_EVENT_TYPES | {"heartbeat"}))
    occurred_at = serializers.DateTimeField(required=False)
    detail = serializers.DictField(required=False, default=dict)

    def validate_detail(self, value):
        if len(str(value)) > 1000:
            raise serializers.ValidationError("Detail is too large.")
        return value


class AttemptEventsView(APIView):
    permission_classes = [IsStudent]
    throttle_classes = [EventThrottle]

    def post(self, request, attempt_id):
        s = EventSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            state = services.handle_event(request, attempt_id, s.validated_data["type"], s.validated_data["detail"], s.validated_data.get("occurred_at"))
        except services.AttemptError as exc:
            return _error(exc)
        return Response(state)


class SubmitAttemptView(APIView):
    permission_classes = [IsStudent]
    throttle_classes = [AnswerThrottle]

    def post(self, request, attempt_id):
        try:
            attempt = services.load_attempt(request, attempt_id)
            if attempt.is_open and not services.expire_if_due(attempt):
                services.enforce_device(request, attempt)
                services.submit(attempt, Attempt.SubmitReason.STUDENT)
        except services.AttemptError as exc:
            return _error(exc)
        attempt.refresh_from_db()
        # Deliberately no score: results stay hidden until the admin publishes them.
        return Response({"status": attempt.status, "submit_reason": attempt.submit_reason, "submitted_at": attempt.submitted_at})


# --- Admin: monitor & interventions --------------------------------------------------------------


def _student_state(attempt, now):
    if attempt is None:
        return "not_started"
    if attempt.status == Attempt.Status.SUBMITTED:
        return "submitted"
    if attempt.last_seen_at and now - attempt.last_seen_at > timedelta(seconds=settings.EXAM_DISCONNECT_SECONDS):
        return "disconnected"
    return "in_progress"


class ExamMonitorView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def get(self, request, exam_id):
        exam = get_object_or_404(Exam.objects.select_related("subject"), pk=exam_id)
        now = timezone.now()
        section_ids = list(exam.targets.values_list("section_id", flat=True))
        profiles = StudentProfile.objects.filter(section_id__in=section_ids, user__is_active=True).select_related("user", "section__school_class")
        attempts = {a.student_id: a for a in Attempt.objects.filter(exam=exam)}
        answered = _answer_counts(exam)
        rows, counts = [], {"not_started": 0, "in_progress": 0, "disconnected": 0, "submitted": 0}
        for p in profiles:
            attempt = attempts.get(p.user_id)
            state = _student_state(attempt, now)
            counts[state] += 1
            rows.append(
                {
                    "student_id": p.user_id,
                    "roll_no": p.roll_no,
                    "name": p.user.full_name,
                    "section": p.section.label,
                    "state": state,
                    "attempt_id": attempt.pk if attempt else None,
                    "started_at": attempt.started_at if attempt else None,
                    "deadline_at": attempt.deadline_at if attempt else None,
                    "submitted_at": attempt.submitted_at if attempt else None,
                    "submit_reason": attempt.submit_reason if attempt else "",
                    "last_seen_at": attempt.last_seen_at if attempt else None,
                    "answered": answered.get(attempt.pk, 0) if attempt else 0,
                    "total_questions": len(attempt.question_order) if attempt else None,
                    "flag_count": attempt.flag_count if attempt else 0,
                    "fullscreen_exits": attempt.fullscreen_exits if attempt else 0,
                    "ip": attempt.ip if attempt else None,
                }
            )
        return Response(
            {
                "exam": {"id": exam.pk, "title": exam.title, "status": exam.effective_status, "start_at": exam.start_at, "end_at": exam.end_at},
                "server_time": now,
                "counts": counts,
                "students": rows,
            }
        )


def _answer_counts(exam):
    return dict(
        AttemptAnswer.objects.filter(attempt__exam=exam)
        .values("attempt_id")
        .annotate(n=Count("id"))
        .values_list("attempt_id", "n")
    )


class InterventionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, min_length=3)
    minutes = serializers.IntegerField(min_value=1, max_value=240, required=False)


class AttemptInterventionView(APIView):
    """extend / terminate / reset / release-device. Reason required; always audited."""

    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request, attempt_id, op):
        s = InterventionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reason = s.validated_data["reason"]
        attempt = get_object_or_404(Attempt.objects.select_related("exam"), pk=attempt_id)
        before = {"status": attempt.status, "deadline_at": attempt.deadline_at, "score": attempt.score, "device_id": bool(attempt.device_id)}

        if op == "extend":
            minutes = s.validated_data.get("minutes")
            if not minutes:
                return Response({"detail": "minutes is required."}, status=status.HTTP_400_BAD_REQUEST)
            if not attempt.is_open:
                return Response({"detail": "Only an attempt in progress can be extended."}, status=status.HTTP_409_CONFLICT)
            attempt.deadline_at += timedelta(minutes=minutes)
            attempt.save(update_fields=["deadline_at"])
            after = {"deadline_at": attempt.deadline_at, "minutes": minutes}
        elif op == "terminate":
            if not attempt.is_open:
                return Response({"detail": "Attempt is already submitted."}, status=status.HTTP_409_CONFLICT)
            services.submit(attempt, Attempt.SubmitReason.ADMIN)
            after = {"status": attempt.status, "score": attempt.score}
        elif op == "reset":
            if attempt.exam.status == Exam.Status.PUBLISHED or attempt.exam.publications.filter(section_id=attempt.section_id).exists():
                return Response({"detail": "Results for this section are already published."}, status=status.HTTP_409_CONFLICT)
            before.update(
                answers=attempt.answers.count(),
                events=list(attempt.events.values("type", "occurred_at")[:200]),
                flag_count=attempt.flag_count,
                student_id=attempt.student_id,
            )
            attempt.delete()
            after = {"deleted": True}
        elif op == "release-device":
            attempt.device_id = ""
            attempt.save(update_fields=["device_id"])
            after = {"device_id": False}
        else:
            return Response({"detail": "Unknown action."}, status=status.HTTP_404_NOT_FOUND)

        audit(request, f"attempt.{op}", "attempts", attempt_id, before=before, after=after, reason=reason)
        return Response({"detail": "Done.", "op": op, **after})


class AttemptReviewView(APIView):
    """Post-exam review for one attempt: answers with keys, proctor timeline, late changes."""

    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def get(self, request, attempt_id):
        attempt = get_object_or_404(Attempt.objects.select_related("exam", "student__student_profile__section__school_class"), pk=attempt_id)
        from apps.results.services import answer_review

        review = answer_review(attempt, reveal=True)
        events = list(attempt.events.values("type", "occurred_at", "client_time", "detail"))
        late_window = timedelta(seconds=30)
        late_changes = 0
        if attempt.submitted_at:
            late_changes = attempt.answers.filter(answered_at__gte=attempt.submitted_at - late_window).count()
        by_type = {}
        for e in events:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        profile = attempt.student.student_profile
        return Response(
            {
                "attempt": {
                    "id": attempt.pk,
                    "student": {"id": attempt.student_id, "name": attempt.student.full_name, "roll_no": profile.roll_no, "section": profile.section.label},
                    "status": attempt.status,
                    "submit_reason": attempt.submit_reason,
                    "started_at": attempt.started_at,
                    "deadline_at": attempt.deadline_at,
                    "submitted_at": attempt.submitted_at,
                    "score": attempt.score,
                    "max_score": attempt.max_score,
                    "grading_status": attempt.grading_status,
                    "rank": attempt.rank,
                    "flag_count": attempt.flag_count,
                    "fullscreen_exits": attempt.fullscreen_exits,
                    "ip": attempt.ip,
                    "user_agent": attempt.user_agent,
                },
                "flags": {"by_type": by_type, "timeline": events, "answers_changed_last_30s": late_changes},
                "questions": review,
            }
        )


class MarkingQueueView(APIView):
    """Short answers awaiting (or open to) manual marking for one exam."""

    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def get(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        qs = (
            AttemptAnswer.objects.filter(attempt__exam=exam, attempt__status=Attempt.Status.SUBMITTED, question__type=Question.Type.SHORT_ANSWER)
            .select_related("question", "attempt")
            .order_by("question_id", "attempt_id")
        )
        if request.query_params.get("pending") != "false":
            qs = qs.filter(marks_awarded__isnull=True)
        rows = []
        for a in qs[:500]:
            entry = a.attempt.entry(a.question_id) or {}
            rows.append(
                {
                    "answer_id": a.pk,
                    "attempt_id": a.attempt_id,
                    "question_id": a.question_id,
                    "question_text": a.question.text,
                    "explanation": a.question.explanation,
                    "max_marks": entry.get("marks"),
                    "text": a.answer.get("text", ""),
                    "marks_awarded": a.marks_awarded,
                }
            )
        return Response({"results": rows, "pending": AttemptAnswer.objects.filter(attempt__exam=exam, question__type=Question.Type.SHORT_ANSWER, marks_awarded__isnull=True, attempt__status=Attempt.Status.SUBMITTED).count()})


class MarkSerializer(serializers.Serializer):
    marks_awarded = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class MarkAnswerView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request, answer_id):
        s = MarkSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        answer = get_object_or_404(AttemptAnswer.objects.select_related("attempt__exam", "question"), pk=answer_id)
        if answer.question.type != Question.Type.SHORT_ANSWER:
            return Response({"detail": "Only short answers are marked by hand."}, status=status.HTTP_400_BAD_REQUEST)
        if answer.attempt.status != Attempt.Status.SUBMITTED:
            return Response({"detail": "Attempt is still in progress."}, status=status.HTTP_409_CONFLICT)
        entry = answer.attempt.entry(answer.question_id)
        max_marks = Decimal(str(entry["marks"])) if entry else answer.question.marks
        marks = s.validated_data["marks_awarded"]
        if marks > max_marks:
            return Response({"detail": f"Marks cannot exceed {max_marks}."}, status=status.HTTP_400_BAD_REQUEST)
        before = {"marks_awarded": answer.marks_awarded}
        answer.marks_awarded = marks
        answer.is_correct = marks == max_marks if marks > 0 else False
        answer.marked_by = request.user
        answer.save(update_fields=["marks_awarded", "is_correct", "marked_by"])
        attempt = recompute_score(answer.attempt)
        refresh_exam_grading_state(answer.attempt.exam)
        from apps.results.services import recompute_ranks_if_published

        recompute_ranks_if_published(answer.attempt.exam)
        audit(request, "answer.mark", "attempt_answers", answer.pk, before=before, after={"marks_awarded": marks}, reason=s.validated_data.get("reason", ""))
        return Response({"answer_id": answer.pk, "marks_awarded": marks, "attempt_score": attempt.score, "grading_status": attempt.grading_status})


# --- Internal (cron) -----------------------------------------------------------------------------


class SweepAttemptsView(APIView):
    authentication_classes = []
    permission_classes = [InternalSecret]
    throttle_classes = [InternalThrottle]

    def post(self, request):
        return Response({"auto_submitted": services.sweep_expired()})


class WarmupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [InternalThrottle]

    def get(self, request):
        return self.post(request)

    def post(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"ok": True, "time": timezone.now()})
