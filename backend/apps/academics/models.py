from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class AcademicYear(models.Model):
    label = models.CharField(max_length=16, unique=True)  # e.g. "2026-27"
    is_current = models.BooleanField(default=False)

    class Meta:
        db_table = "academic_years"
        ordering = ["-label"]
        constraints = [
            models.UniqueConstraint(fields=["is_current"], condition=Q(is_current=True), name="one_current_academic_year")
        ]

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first()

    def __str__(self):
        return self.label


class SchoolClass(models.Model):
    grade = models.PositiveSmallIntegerField(unique=True, validators=[MinValueValidator(1), MaxValueValidator(12)])

    class Meta:
        db_table = "classes"
        ordering = ["grade"]
        verbose_name_plural = "classes"

    @property
    def simple_mode(self):
        """Classes 1–3 get large buttons and fewer anti-cheat prompts."""
        return self.grade <= 3

    def __str__(self):
        return f"Class {self.grade}"


class Section(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=8)

    class Meta:
        db_table = "sections"
        ordering = ["school_class__grade", "name"]
        constraints = [models.UniqueConstraint(fields=["school_class", "name"], name="unique_section_per_class")]

    @property
    def label(self):
        return f"{self.school_class.grade}-{self.name}"

    def __str__(self):
        return self.label


class Subject(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=64)

    class Meta:
        db_table = "subjects"
        ordering = ["school_class__grade", "name"]
        constraints = [models.UniqueConstraint(fields=["school_class", "name"], name="unique_subject_per_class")]

    def __str__(self):
        return f"{self.name} ({self.school_class.grade})"


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="chapters")
    name = models.CharField(max_length=128)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "chapters"
        ordering = ["subject", "order", "id"]

    def __str__(self):
        return self.name
