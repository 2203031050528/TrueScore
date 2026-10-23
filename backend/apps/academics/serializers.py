from rest_framework import serializers

from .models import AcademicYear, Chapter, SchoolClass, Section, Subject


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["id", "label", "is_current"]
        read_only_fields = ["is_current"]


class SectionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    student_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Section
        fields = ["id", "school_class", "name", "label", "student_count"]

    def validate_name(self, value):
        value = value.strip().upper()
        if not value.isalpha():
            raise serializers.ValidationError("Section name must be letters only (A, B, C…).")
        return value


class ChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = ["id", "subject", "name", "order"]


class SubjectSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(many=True, read_only=True)
    grade = serializers.IntegerField(source="school_class.grade", read_only=True)

    class Meta:
        model = Subject
        fields = ["id", "school_class", "grade", "name", "chapters"]


class SchoolClassSerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, read_only=True)
    subjects = serializers.SerializerMethodField()

    class Meta:
        model = SchoolClass
        fields = ["id", "grade", "simple_mode", "sections", "subjects"]

    def get_subjects(self, obj):
        return [{"id": s.id, "name": s.name} for s in obj.subjects.all()]
