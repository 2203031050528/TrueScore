from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import audit
from apps.core.permissions import IsStudent
from apps.core.viewsets import AuditedAdminViewSet

from .models import AcademicYear, Chapter, SchoolClass, Section, Subject
from .serializers import (
    AcademicYearSerializer,
    ChapterSerializer,
    SchoolClassSerializer,
    SectionSerializer,
    SubjectSerializer,
)


class AcademicYearViewSet(AuditedAdminViewSet):
    serializer_class = AcademicYearSerializer
    queryset = AcademicYear.objects.all()
    http_method_names = ["get", "post", "head", "options"]

    @action(detail=True, methods=["post"], url_path="set-current")
    def set_current(self, request, pk=None):
        year = self.get_object()
        with transaction.atomic():
            AcademicYear.objects.filter(is_current=True).update(is_current=False)
            year.is_current = True
            year.save(update_fields=["is_current"])
        audit(request, "academic_years.set_current", "academic_years", year.pk)
        return Response(AcademicYearSerializer(year).data)


class SchoolClassViewSet(AuditedAdminViewSet):
    serializer_class = SchoolClassSerializer
    queryset = SchoolClass.objects.prefetch_related("sections__school_class", "subjects")
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = None


class SectionViewSet(AuditedAdminViewSet):
    serializer_class = SectionSerializer

    def get_queryset(self):
        qs = Section.objects.select_related("school_class").annotate(
            student_count=Count("students", filter=Q(students__user__is_active=True))
        )
        if self.request.query_params.get("class_id"):
            qs = qs.filter(school_class_id=self.request.query_params["class_id"])
        return qs

    def perform_destroy(self, instance):
        if instance.students.exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": "Move the students out of this section before deleting it."})
        super().perform_destroy(instance)


class SubjectViewSet(AuditedAdminViewSet):
    serializer_class = SubjectSerializer

    def get_queryset(self):
        qs = Subject.objects.select_related("school_class").prefetch_related("chapters")
        if self.request.query_params.get("class_id"):
            qs = qs.filter(school_class_id=self.request.query_params["class_id"])
        return qs


class ChapterViewSet(AuditedAdminViewSet):
    serializer_class = ChapterSerializer

    def get_queryset(self):
        qs = Chapter.objects.select_related("subject")
        if self.request.query_params.get("subject_id"):
            qs = qs.filter(subject_id=self.request.query_params["subject_id"])
        return qs


class StudentSubjectsView(generics.ListAPIView):
    """Subjects and chapters of the logged-in student's own class."""

    permission_classes = [IsStudent]
    serializer_class = SubjectSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Subject.objects.filter(school_class_id=self.request.user.student_profile.school_class_id)
            .select_related("school_class")
            .prefetch_related("chapters")
        )

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset(), many=True).data, status=status.HTTP_200_OK)
