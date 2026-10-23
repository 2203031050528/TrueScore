from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import F


class TrueScoreUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    first_name = None
    last_name = None
    full_name = models.CharField(max_length=128, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT, db_index=True)
    token_version = models.PositiveIntegerField(default=0)
    must_change_password = models.BooleanField(default=False)

    objects = TrueScoreUserManager()

    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    def bump_token_version(self):
        """Invalidate every access and refresh token issued to this user (force logout everywhere)."""
        User.objects.filter(pk=self.pk).update(token_version=F("token_version") + 1)
        self.refresh_from_db(fields=["token_version"])

    def __str__(self):
        return self.username


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile", primary_key=True)
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.PROTECT, related_name="students")
    roll_no = models.CharField(max_length=32)
    school_class = models.ForeignKey("academics.SchoolClass", on_delete=models.PROTECT, related_name="students")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="students")
    guardian_phone = models.CharField(max_length=20, blank=True)
    photo_key = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "student_profiles"
        ordering = ["school_class__grade", "section__name", "roll_no"]
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "roll_no"], name="unique_roll_no_per_year"),
        ]
        indexes = [models.Index(fields=["section"])]

    def __str__(self):
        return f"{self.roll_no} ({self.section})"
