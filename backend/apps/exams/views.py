from django.db.models import Prefetch, Q
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.audit.services import audit
from apps.core.viewsets import AuditedAdminViewSet

from . import services
from .models import Exam, ExamPart, ExamQuestion, Question
from .serializers import ExamPartSerializer, ExamQuestionSerializer, ExamSerializer, QuestionSerializer


def _bad_request(exc):
    payload = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {"detail": str(exc)}
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)


class QuestionViewSet(AuditedAdminViewSet):
    serializer_class = QuestionSerializer
    audit_entity = "questions"

    def get_queryset(self):
        qs = Question.objects.select_related("subject__school_class", "chapter").prefetch_related("options")
        p = self.request.query_params
        if p.get("include_inactive") != "true":
            qs = qs.filter(is_active=True)
        for param, field in [("class_id", "subject__school_class_id"), ("subject_id", "subject_id"), ("chapter_id", "chapter_id"), ("difficulty", "difficulty"), ("type", "type")]:
            if p.get(param):
                qs = qs.filter(**{field: p[param]})
        if p.get("search"):
            qs = qs.filter(text__icontains=p["search"].strip())
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        audit(self.request, "questions.create", "questions", obj.pk, after=serializer.data)

    def update(self, request, *args, **kwargs):
        question = self.get_object()
        if not question.is_locked():
            return super().update(request, *args, **kwargs)
        # Used in a scheduled exam: keep history intact and create a new version instead.
        serializer = self.get_serializer(question, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        options = data.pop("options", None)
        new = services.new_question_version(question, data, options, request.user)
        out = QuestionSerializer(new).data
        audit(request, "questions.new_version", "questions", new.pk, before={"id": question.pk}, after=out)
        return Response({**out, "versioned_from": question.pk}, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.exam_links.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            audit(self.request, "questions.deactivate", "questions", instance.pk)
            return
        super().perform_destroy(instance)

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Upload a CSV file in the 'file' field."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            count = services.import_questions(uploaded, request.user)
        except services.ExamError as exc:
            return _bad_request(exc)
        audit(request, "questions.import", "questions", "", after={"count": count})
        return Response({"created": count}, status=status.HTTP_201_CREATED)


class ExamViewSet(AuditedAdminViewSet):
    serializer_class = ExamSerializer
    audit_entity = "exams"

    def get_queryset(self):
        qs = Exam.objects.select_related("subject", "school_class").prefetch_related(
            "sections__school_class", Prefetch("parts", queryset=ExamPart.objects.prefetch_related("exam_questions"))
        )
        p = self.request.query_params
        if p.get("class_id"):
            qs = qs.filter(school_class_id=p["class_id"])
        if p.get("subject_id"):
            qs = qs.filter(subject_id=p["subject_id"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("search"):
            qs = qs.filter(Q(title__icontains=p["search"].strip()))
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        audit(self.request, "exams.create", "exams", obj.pk, after=serializer.data)

    def perform_destroy(self, instance):
        if instance.status != Exam.Status.DRAFT:
            raise ValidationError({"detail": "Only draft exams can be deleted."})
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        exam = self.get_object()
        part = None
        if request.data.get("part_id"):
            part = exam.parts.filter(pk=request.data["part_id"]).first()
            if part is None:
                return Response({"detail": "Part not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            result = services.generate(exam, part)
        except services.ExamError as exc:
            return _bad_request(exc)
        audit(request, "exams.generate", "exams", exam.pk, after=result)
        return Response({"generated": result, "exam": ExamSerializer(self.get_object()).data})

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        exam = self.get_object()
        try:
            exam = services.schedule(exam)
        except services.ExamError as exc:
            return _bad_request(exc)
        data = ExamSerializer(self.get_object()).data
        audit(request, "exams.schedule", "exams", exam.pk, after={"total_marks": str(exam.total_marks), "start_at": exam.start_at, "end_at": exam.end_at})
        return Response(data)

    @action(detail=True, methods=["post"])
    def unschedule(self, request, pk=None):
        exam = self.get_object()
        try:
            exam = services.unschedule(exam)
        except services.ExamError as exc:
            return _bad_request(exc)
        audit(request, "exams.unschedule", "exams", exam.pk, reason=request.data.get("reason", ""))
        return Response(ExamSerializer(self.get_object()).data)

    @action(detail=True, methods=["get"])
    def paper(self, request, pk=None):
        """Admin preview of the full paper, with answer keys."""
        exam = self.get_object()
        eqs = ExamQuestion.objects.filter(exam=exam).select_related("part", "question__chapter", "question__subject__school_class").prefetch_related("question__options")
        return Response(
            {
                "exam": ExamSerializer(exam).data,
                "questions": ExamQuestionSerializer(eqs, many=True).data,
            }
        )


class ExamPartViewSet(AuditedAdminViewSet):
    serializer_class = ExamPartSerializer
    audit_entity = "exam_parts"

    def get_queryset(self):
        qs = ExamPart.objects.select_related("exam")
        if self.request.query_params.get("exam_id"):
            qs = qs.filter(exam_id=self.request.query_params["exam_id"])
        return qs

    def perform_destroy(self, instance):
        if instance.exam.paper_locked:
            raise ValidationError({"detail": "The paper is locked once the exam is scheduled."})
        super().perform_destroy(instance)


class ExamQuestionWriteSerializer(ExamQuestionSerializer):
    marks = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)

    class Meta(ExamQuestionSerializer.Meta):
        read_only_fields = []

    def validate(self, attrs):
        part = attrs.get("part") or self.instance.part
        exam = attrs.get("exam") or part.exam
        question = attrs.get("question") or self.instance.question
        if part.exam_id != exam.pk:
            raise serializers.ValidationError({"part": "Part belongs to another exam."})
        if exam.paper_locked:
            raise serializers.ValidationError("The paper is locked once the exam is scheduled.")
        if question.subject_id != exam.subject_id:
            raise serializers.ValidationError({"question": "Question is from a different subject."})
        if not question.is_active:
            raise serializers.ValidationError({"question": "Question is inactive."})
        dupes = ExamQuestion.objects.filter(exam=exam, question=question)
        if self.instance:
            dupes = dupes.exclude(pk=self.instance.pk)
        if dupes.exists():
            raise serializers.ValidationError({"question": "Question is already on this paper."})
        if attrs.get("marks") is None and not self.instance:
            attrs["marks"] = question.marks
        if attrs.get("marks") is not None and attrs["marks"] <= 0:
            raise serializers.ValidationError({"marks": "Marks must be greater than zero."})
        attrs["exam"] = exam
        return attrs


class ExamQuestionViewSet(AuditedAdminViewSet):
    """Hand-picking questions into a part of a draft exam."""

    audit_entity = "exam_questions"

    def get_serializer_class(self):
        return ExamQuestionSerializer if self.action in {"list", "retrieve"} else ExamQuestionWriteSerializer

    def get_queryset(self):
        qs = ExamQuestion.objects.select_related("part", "exam", "question__chapter", "question__subject__school_class").prefetch_related("question__options")
        if self.request.query_params.get("exam_id"):
            qs = qs.filter(exam_id=self.request.query_params["exam_id"])
        if self.request.query_params.get("part_id"):
            qs = qs.filter(part_id=self.request.query_params["part_id"])
        return qs

    def perform_destroy(self, instance):
        if instance.exam.paper_locked:
            raise ValidationError({"detail": "The paper is locked once the exam is scheduled."})
        super().perform_destroy(instance)
