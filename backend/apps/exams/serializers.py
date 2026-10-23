"""Admin serializers. These include answer keys and must never be used in student-facing views."""

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.academics.models import Chapter, Section, Subject
from apps.core.storage import StorageError, get_storage, validate_key

from .models import DEFAULT_EXAM_SETTINGS, SIMPLE_MODE_SETTINGS, Exam, ExamPart, ExamQuestion, Question, QuestionOption


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ["id", "text", "is_correct", "order"]
        read_only_fields = ["id"]


class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.select_related("school_class"))
    chapter = serializers.PrimaryKeyRelatedField(queryset=Chapter.objects.all())
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    grade = serializers.IntegerField(source="subject.school_class.grade", read_only=True)
    image_url = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "subject",
            "subject_name",
            "grade",
            "chapter",
            "chapter_name",
            "type",
            "text",
            "image_key",
            "image_url",
            "difficulty",
            "marks",
            "negative_marks",
            "explanation",
            "numeric_answer",
            "numeric_tolerance",
            "is_active",
            "version",
            "parent",
            "options",
            "locked",
            "created_at",
        ]
        read_only_fields = ["is_active", "version", "parent", "created_at"]

    def get_image_url(self, obj):
        return get_storage().download_url(obj.image_key, 600) if obj.image_key else None

    def get_locked(self, obj):
        return obj.is_locked() if obj.pk else False

    def validate_image_key(self, value):
        if not value or (self.instance and self.instance.image_key == value):
            return value
        try:
            validate_key(value)
        except StorageError as exc:
            raise serializers.ValidationError(str(exc)) from None
        if not value.startswith("questions/") or not get_storage().exists(value):
            raise serializers.ValidationError("Upload the image first.")
        return value

    def validate(self, attrs):
        get = lambda name, default=None: attrs.get(name, getattr(self.instance, name, default) if self.instance else default)  # noqa: E731
        subject, chapter, qtype = get("subject"), get("chapter"), get("type")
        if chapter and subject and chapter.subject_id != subject.pk:
            raise serializers.ValidationError({"chapter": "Chapter does not belong to this subject."})
        marks, negative = get("marks", Decimal("1")), get("negative_marks", Decimal("0"))
        if marks is not None and marks <= 0:
            raise serializers.ValidationError({"marks": "Marks must be greater than zero."})
        if negative is not None and negative < 0:
            raise serializers.ValidationError({"negative_marks": "Negative marks cannot be below zero."})

        options = attrs.get("options")
        if options is None and self.instance is not None and "type" not in attrs:
            return attrs  # options untouched
        if options is None:
            options = [] if self.instance is None else [
                {"text": o.text, "is_correct": o.is_correct, "order": o.order} for o in self.instance.options.all()
            ]
        correct = sum(1 for o in options if o.get("is_correct"))
        if qtype in Question.OPTION_TYPES:
            if qtype == Question.Type.TRUE_FALSE and len(options) != 2:
                raise serializers.ValidationError({"options": "True/false questions need exactly two options."})
            if len(options) < 2:
                raise serializers.ValidationError({"options": "Add at least two options."})
            if len(options) > 8:
                raise serializers.ValidationError({"options": "At most eight options."})
            if qtype == Question.Type.MCQ_MULTI and correct < 1:
                raise serializers.ValidationError({"options": "Mark at least one correct option."})
            if qtype != Question.Type.MCQ_MULTI and correct != 1:
                raise serializers.ValidationError({"options": "Mark exactly one correct option."})
        elif options:
            raise serializers.ValidationError({"options": "This question type has no options."})
        if qtype == Question.Type.NUMERIC and get("numeric_answer") is None:
            raise serializers.ValidationError({"numeric_answer": "Numeric questions need the correct value."})
        attrs["options"] = options
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        options = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        self._write_options(question, options)
        return question

    @transaction.atomic
    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if options is not None:
            instance.options.all().delete()
            self._write_options(instance, options)
        return instance

    @staticmethod
    def _write_options(question, options):
        QuestionOption.objects.bulk_create(
            [
                QuestionOption(question=question, text=o["text"], is_correct=bool(o.get("is_correct")), order=o.get("order", i))
                for i, o in enumerate(options)
            ]
        )


class ExamQuestionSerializer(serializers.ModelSerializer):
    question_detail = QuestionSerializer(source="question", read_only=True)

    class Meta:
        model = ExamQuestion
        fields = ["id", "exam", "part", "question", "order", "marks", "question_detail"]
        read_only_fields = ["exam"]


class ExamPartSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = ExamPart
        fields = ["id", "exam", "name", "order", "instructions", "rule", "question_count"]

    def get_question_count(self, part):
        return part.exam_questions.count()

    def validate_rule(self, rule):
        if not isinstance(rule, dict):
            raise serializers.ValidationError("Rule must be an object.")
        clean = {}
        for difficulty in Question.Difficulty.values:
            value = rule.get(difficulty, 0)
            if not isinstance(value, int) or not 0 <= value <= 200:
                raise serializers.ValidationError(f"'{difficulty}' must be a whole number 0–200.")
            clean[difficulty] = value
        chapters = rule.get("chapters") or []
        if not isinstance(chapters, list) or not all(isinstance(c, int) for c in chapters):
            raise serializers.ValidationError("'chapters' must be a list of chapter ids.")
        clean["chapters"] = chapters
        clean["per_student"] = bool(rule.get("per_student", False))
        marks = rule.get("marks") or {}
        if not isinstance(marks, dict) or any(k not in Question.Difficulty.values for k in marks):
            raise serializers.ValidationError("'marks' must map easy/medium/hard to numbers.")
        try:
            clean["marks"] = {k: float(v) for k, v in marks.items() if float(v) > 0}
        except (TypeError, ValueError):
            raise serializers.ValidationError("'marks' values must be numbers.") from None
        return clean

    def validate(self, attrs):
        exam = attrs.get("exam") or self.instance.exam
        if exam.paper_locked:
            raise serializers.ValidationError("The paper is locked once the exam is scheduled.")
        if self.instance and "exam" in attrs and attrs["exam"] != self.instance.exam:
            raise serializers.ValidationError({"exam": "A part cannot move to another exam."})
        chapters = (attrs.get("rule") or {}).get("chapters") or []
        if chapters and Chapter.objects.filter(pk__in=chapters, subject=exam.subject).count() != len(set(chapters)):
            raise serializers.ValidationError({"rule": "All chapters must belong to the exam's subject."})
        return attrs


class ExamSerializer(serializers.ModelSerializer):
    section_ids = serializers.PrimaryKeyRelatedField(
        source="sections", many=True, queryset=Section.objects.all(), required=False
    )
    sections_label = serializers.SerializerMethodField()
    effective_status = serializers.CharField(read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    grade = serializers.IntegerField(source="school_class.grade", read_only=True)
    parts = ExamPartSerializer(many=True, read_only=True)
    attempt_count = serializers.SerializerMethodField()

    # Fields that can still change after the paper is locked.
    MUTABLE_WHEN_LOCKED = {"title", "instructions", "settings", "end_at"}

    class Meta:
        model = Exam
        fields = [
            "id",
            "title",
            "school_class",
            "grade",
            "subject",
            "subject_name",
            "instructions",
            "start_at",
            "end_at",
            "duration_min",
            "total_marks",
            "pass_marks",
            "status",
            "effective_status",
            "settings",
            "section_ids",
            "sections_label",
            "parts",
            "attempt_count",
            "scheduled_at",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["total_marks", "status", "scheduled_at", "published_at", "created_at"]

    def get_sections_label(self, exam):
        return [s.label for s in exam.sections.all()]

    def get_attempt_count(self, exam):
        return exam.attempts.count()

    def validate_settings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Settings must be an object.")
        unknown = set(value) - set(DEFAULT_EXAM_SETTINGS)
        if unknown:
            raise serializers.ValidationError(f"Unknown settings: {', '.join(sorted(unknown))}")
        if "max_fullscreen_exits" in value and (not isinstance(value["max_fullscreen_exits"], int) or value["max_fullscreen_exits"] < 0):
            raise serializers.ValidationError("max_fullscreen_exits must be a whole number ≥ 0.")
        if "ip_allowlist" in value:
            import ipaddress

            if not isinstance(value["ip_allowlist"], list):
                raise serializers.ValidationError("ip_allowlist must be a list.")
            for entry in value["ip_allowlist"]:
                try:
                    ipaddress.ip_network(str(entry), strict=False)
                except ValueError:
                    raise serializers.ValidationError(f"'{entry}' is not a valid IP or CIDR.") from None
        if "access_code" in value and len(str(value["access_code"])) > 32:
            raise serializers.ValidationError("Access code is too long.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.paper_locked:
            locked = {k for k in attrs if k not in self.MUTABLE_WHEN_LOCKED}
            if locked:
                raise serializers.ValidationError(
                    {"detail": f"Paper is locked; these fields cannot change now: {', '.join(sorted(locked))}."}
                )
            if "end_at" in attrs and attrs["end_at"] < instance.end_at:
                raise serializers.ValidationError({"end_at": "A scheduled exam's window can only be extended."})
        get = lambda k: attrs.get(k, getattr(instance, k, None))  # noqa: E731
        school_class, subject = get("school_class"), get("subject")
        if subject and school_class and subject.school_class_id != school_class.pk:
            raise serializers.ValidationError({"subject": "Subject does not belong to this class."})
        start, end, duration = get("start_at"), get("end_at"), get("duration_min")
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "End must be after start."})
        if duration is not None and not 1 <= duration <= 600:
            raise serializers.ValidationError({"duration_min": "Duration must be 1–600 minutes."})
        sections = attrs.get("sections")
        if sections is not None and school_class and any(s.school_class_id != school_class.pk for s in sections):
            raise serializers.ValidationError({"section_ids": "All sections must belong to the exam's class."})
        if attrs.get("pass_marks") is not None and attrs["pass_marks"] < 0:
            raise serializers.ValidationError({"pass_marks": "Pass marks cannot be negative."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        sections = validated_data.pop("sections", [])
        settings = validated_data.get("settings") or {}
        if validated_data["school_class"].simple_mode:
            settings = {**SIMPLE_MODE_SETTINGS, **settings}
        validated_data["settings"] = settings
        exam = Exam.objects.create(**validated_data)
        exam.sections.set(sections)
        return exam

    @transaction.atomic
    def update(self, instance, validated_data):
        sections = validated_data.pop("sections", None)
        if "settings" in validated_data:
            validated_data["settings"] = {**(instance.settings or {}), **validated_data["settings"]}
        exam = super().update(instance, validated_data)
        if sections is not None:
            exam.sections.set(sections)
        return exam

    def to_representation(self, exam):
        data = super().to_representation(exam)
        # Access code and SEB key are shown to admins (they set them) but never echoed into audit logs.
        data["settings"] = exam.effective_settings
        return data
