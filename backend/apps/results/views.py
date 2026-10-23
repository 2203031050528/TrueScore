from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attempts.models import Attempt
from apps.audit.services import audit
from apps.core.permissions import IsAdmin, IsStudent
from apps.core.throttles import AdminThrottle
from apps.exams.models import Exam

from . import services
from .models import ResultPublication


class ProgressView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        return Response(services.progress_dashboard(request.user))


class StudentResultListView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        attempts = list(services.published_attempts(request.user).order_by("-exam__start_at"))
        pubs = {(p.exam_id, p.section_id): p for p in ResultPublication.objects.filter(exam__in=[a.exam_id for a in attempts])}
        sizes = services.section_sizes(attempts)
        return Response(
            [services.result_summary(a, pubs[(a.exam_id, a.section_id)], sizes.get((a.exam_id, a.section_id), 0)) for a in attempts]
        )


class StudentResultDetailView(APIView):
    """403 until a publication exists for this exam and the student's section — enforced here, not in the UI."""

    permission_classes = [IsStudent]

    def get(self, request, exam_id):
        attempt = Attempt.objects.filter(exam_id=exam_id, student=request.user).select_related("exam__subject").first()
        if attempt is None:
            return Response({"detail": "You did not take this exam.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        publication = ResultPublication.objects.filter(exam_id=exam_id, section_id=attempt.section_id).first()
        if publication is None or attempt.status != Attempt.Status.SUBMITTED:
            return Response({"detail": "Results have not been published yet.", "code": "not_published"}, status=status.HTTP_403_FORBIDDEN)
        sizes = services.section_sizes([attempt])
        summary = services.result_summary(attempt, publication, sizes.get((attempt.exam_id, attempt.section_id), 0))
        review = services.answer_review(attempt, reveal=True) if summary["show_answers"] else None
        return Response({**summary, "questions": review})


class AnalyticsView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def get(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        return Response(services.analytics(exam))


class ExamAttemptsView(APIView):
    """Admin result sheet: every submitted attempt with score and rank."""

    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def get(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        qs = Attempt.objects.filter(exam=exam).select_related("student__student_profile", "section__school_class").order_by("section__name", "-score")
        if request.query_params.get("section_id"):
            qs = qs.filter(section_id=request.query_params["section_id"])
        return Response(
            [
                {
                    "attempt_id": a.pk,
                    "student_id": a.student_id,
                    "roll_no": a.student.student_profile.roll_no,
                    "name": a.student.full_name,
                    "section": a.section.label,
                    "status": a.status,
                    "submit_reason": a.submit_reason,
                    "score": a.score,
                    "max_score": a.max_score,
                    "percentage": services.pct(a.score, a.max_score),
                    "passed": a.score is not None and a.score >= exam.pass_marks,
                    "rank": a.rank,
                    "grading_status": a.grading_status,
                    "flag_count": a.flag_count,
                    "submitted_at": a.submitted_at,
                }
                for a in qs
            ]
        )


class PublishSerializer(serializers.Serializer):
    section_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    show_answers = serializers.BooleanField(default=True)


class PublishView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        s = PublishSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            sections = services.publish(exam, s.validated_data.get("section_ids"), s.validated_data["show_answers"], request.user)
        except services.ResultError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, "exam.publish", "exams", exam.pk, after={"section_ids": sections, "show_answers": s.validated_data["show_answers"]})
        exam.refresh_from_db()
        return Response({"published_sections": sections, "exam_status": exam.status})


class UnpublishView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        reason = str(request.data.get("reason", "")).strip()
        if len(reason) < 3:
            return Response({"reason": ["A reason is required."]}, status=status.HTTP_400_BAD_REQUEST)
        removed = services.unpublish(exam, request.data.get("section_ids") or [])
        audit(request, "exam.unpublish", "exams", exam.pk, after={"section_ids": removed}, reason=reason)
        return Response({"unpublished_sections": removed})


class RegradeSerializer(serializers.Serializer):
    question_id = serializers.IntegerField(required=False, allow_null=True)
    correct_option_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    numeric_answer = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)
    numeric_tolerance = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True, min_value=0)
    reason = serializers.CharField(max_length=500, min_length=3)


class RegradeView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        if exam.status == Exam.Status.DRAFT:
            return Response({"detail": "Nothing to re-grade on a draft exam."}, status=status.HTTP_400_BAD_REQUEST)
        s = RegradeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            result = services.fix_key_and_regrade(
                exam, d.get("question_id"), d.get("correct_option_ids"), d.get("numeric_answer"), d.get("numeric_tolerance")
            )
        except services.ResultError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, "exam.regrade", "exams", exam.pk, before=result["before"], after={**(result["after"] or {}), "question_id": d.get("question_id"), "regraded": result["regraded_attempts"]}, reason=d["reason"])
        return Response(result)
