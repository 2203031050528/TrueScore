from django.contrib.auth import password_validation
from django.db import transaction
from rest_framework import serializers

from apps.academics.models import AcademicYear, Section

from .models import StudentProfile, User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "Choose a password different from the current one."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class MeSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "role", "must_change_password", "profile"]

    def get_profile(self, user):
        profile = getattr(user, "student_profile", None)
        if profile is None:
            return None
        return {
            "roll_no": profile.roll_no,
            "class_id": profile.school_class_id,
            "grade": profile.school_class.grade,
            "section_id": profile.section_id,
            "section": profile.section.name,
            "section_label": profile.section.label,
            "academic_year": profile.academic_year.label,
            "guardian_phone": profile.guardian_phone,
            "simple_mode": profile.school_class.simple_mode,
        }


class StudentSerializer(serializers.ModelSerializer):
    """Admin view of a student: the user plus their profile, flattened."""

    roll_no = serializers.CharField(source="student_profile.roll_no", max_length=32)
    section_id = serializers.PrimaryKeyRelatedField(
        source="student_profile.section", queryset=Section.objects.select_related("school_class")
    )
    class_id = serializers.IntegerField(source="student_profile.school_class_id", read_only=True)
    grade = serializers.IntegerField(source="student_profile.school_class.grade", read_only=True)
    section_label = serializers.CharField(source="student_profile.section.label", read_only=True)
    guardian_phone = serializers.CharField(
        source="student_profile.guardian_phone", max_length=20, required=False, allow_blank=True
    )
    academic_year = serializers.CharField(source="student_profile.academic_year.label", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "is_active",
            "must_change_password",
            "last_login",
            "roll_no",
            "class_id",
            "grade",
            "section_id",
            "section_label",
            "guardian_phone",
            "academic_year",
        ]
        read_only_fields = ["id", "username", "is_active", "must_change_password", "last_login"]

    def validate_roll_no(self, value):
        value = value.strip()
        if not value or not value.replace("-", "").replace("_", "").isalnum():
            raise serializers.ValidationError("Roll number may contain only letters, digits, - and _.")
        return value

    def validate(self, attrs):
        profile = attrs.get("student_profile", {})
        roll_no = profile.get("roll_no")
        if roll_no:
            year = self.instance.student_profile.academic_year if self.instance else AcademicYear.current()
            if year is None:
                raise serializers.ValidationError("No current academic year is configured.")
            clash = StudentProfile.objects.filter(academic_year=year, roll_no__iexact=roll_no)
            users = User.objects.filter(username__iexact=roll_no)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
                users = users.exclude(pk=self.instance.pk)
            if clash.exists() or users.exists():
                raise serializers.ValidationError({"roll_no": "This roll number is already in use."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        profile_data = validated_data.pop("student_profile")
        section = profile_data["section"]
        user = User(
            username=profile_data["roll_no"],
            full_name=validated_data.get("full_name", ""),
            role=User.Role.STUDENT,
            must_change_password=True,
        )
        user.set_password(self.context["initial_password"])
        user.save()
        StudentProfile.objects.create(
            user=user,
            academic_year=AcademicYear.current(),
            roll_no=profile_data["roll_no"],
            school_class=section.school_class,
            section=section,
            guardian_phone=profile_data.get("guardian_phone", ""),
        )
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("student_profile", {})
        profile = instance.student_profile
        if "full_name" in validated_data:
            instance.full_name = validated_data["full_name"]
        if "roll_no" in profile_data:
            profile.roll_no = profile_data["roll_no"]
            instance.username = profile_data["roll_no"]
        if "section" in profile_data:
            profile.section = profile_data["section"]
            profile.school_class = profile_data["section"].school_class
        if "guardian_phone" in profile_data:
            profile.guardian_phone = profile_data["guardian_phone"]
        instance.save()
        profile.save()
        return instance


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PromoteSerializer(serializers.Serializer):
    new_year_label = serializers.RegexField(r"^\d{4}-\d{2}$", max_length=16)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
