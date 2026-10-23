"""Seed classes 1–12, sections, subjects and (optionally) demo data for local development.

    python manage.py seed                 # structure only (safe to re-run)
    python manage.py seed --demo          # + demo admin, students, chapters, questions, a live exam
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academics.models import AcademicYear, Chapter, SchoolClass, Section, Subject
from apps.accounts.models import StudentProfile, User
from apps.exams.models import Exam, ExamPart, Question, QuestionOption
from apps.exams.services import generate, schedule

SUBJECTS_PRIMARY = ["English", "Hindi", "Mathematics", "EVS"]
SUBJECTS_MIDDLE = ["English", "Hindi", "Mathematics", "Science", "Social Science"]
SUBJECTS_SENIOR = ["English", "Mathematics", "Physics", "Chemistry", "Biology"]


def subjects_for(grade):
    if grade <= 5:
        return SUBJECTS_PRIMARY
    if grade <= 10:
        return SUBJECTS_MIDDLE
    return SUBJECTS_SENIOR


class Command(BaseCommand):
    help = "Seed academic structure (and optional demo data)."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Create demo admin, students, questions and a live exam.")
        parser.add_argument("--year", default="2026-27")

    @transaction.atomic
    def handle(self, *args, **opts):
        year, _ = AcademicYear.objects.get_or_create(label=opts["year"])
        if not AcademicYear.objects.filter(is_current=True).exists():
            year.is_current = True
            year.save()
        for grade in range(1, 13):
            cls, _ = SchoolClass.objects.get_or_create(grade=grade)
            for name in ["A", "B"]:
                Section.objects.get_or_create(school_class=cls, name=name)
            for subject in subjects_for(grade):
                Subject.objects.get_or_create(school_class=cls, name=subject)
        self.stdout.write(self.style.SUCCESS("Classes 1–12, sections A/B and subjects ready."))
        if opts["demo"]:
            self._demo(year)

    def _demo(self, year):
        admin, created = User.objects.get_or_create(
            username="admin", defaults={"full_name": "School Admin", "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True}
        )
        if created:
            admin.set_password("admin-pass-123")
            admin.save()

        cls8 = SchoolClass.objects.get(grade=8)
        sec_a = Section.objects.get(school_class=cls8, name="A")
        sec_b = Section.objects.get(school_class=cls8, name="B")
        for i in range(1, 7):
            roll = f"8A{i:02d}" if i <= 4 else f"8B{i:02d}"
            user, created = User.objects.get_or_create(
                username=roll, defaults={"full_name": f"Student {roll}", "role": User.Role.STUDENT}
            )
            if created:
                user.set_password("student-pass-123")
                user.save()
                section = sec_a if i <= 4 else sec_b
                StudentProfile.objects.create(user=user, academic_year=year, roll_no=roll, school_class=cls8, section=section)

        maths = Subject.objects.get(school_class=cls8, name="Mathematics")
        chapters = []
        for order, name in enumerate(["Rational Numbers", "Linear Equations", "Squares and Square Roots"], start=1):
            ch, _ = Chapter.objects.get_or_create(subject=maths, name=name, defaults={"order": order})
            chapters.append(ch)

        if not Question.objects.filter(subject=maths).exists():
            bank = [
                ("easy", "What is 3/4 + 1/4?", ["1", "1/2", "3/16", "4/8"], 0),
                ("easy", "Which of these is a rational number?", ["√2", "π", "0.75", "e"], 2),
                ("easy", "What is the additive inverse of 5/7?", ["7/5", "-5/7", "5/7", "-7/5"], 1),
                ("medium", "Solve: 2x + 3 = 11", ["x = 3", "x = 4", "x = 5", "x = 7"], 1),
                ("medium", "Solve: 5x - 2 = 3x + 6", ["x = 2", "x = 3", "x = 4", "x = 8"], 2),
                ("medium", "What is the square of 15?", ["215", "225", "235", "125"], 1),
                ("hard", "What is √1764?", ["38", "42", "44", "48"], 1),
                ("hard", "If 3(x - 2) = 2(x + 1), what is x?", ["4", "6", "8", "10"], 2),
            ]
            for i, (difficulty, text, options, correct) in enumerate(bank):
                q = Question.objects.create(
                    subject=maths, chapter=chapters[i % 3], type=Question.Type.MCQ_SINGLE, text=text, difficulty=difficulty,
                    marks=Decimal("1"), explanation=f"The correct answer is {options[correct]}.", created_by=admin,
                )
                QuestionOption.objects.bulk_create(
                    [QuestionOption(question=q, text=t, is_correct=(j == correct), order=j) for j, t in enumerate(options)]
                )
            q = Question.objects.create(
                subject=maths, chapter=chapters[2], type=Question.Type.NUMERIC, text="What is 12 × 12?",
                difficulty="easy", marks=Decimal("2"), numeric_answer=Decimal("144"), created_by=admin,
            )
            q = Question.objects.create(
                subject=maths, chapter=chapters[1], type=Question.Type.TRUE_FALSE,
                text="x = 2 is a solution of x + 2 = 4.", difficulty="easy", marks=Decimal("1"), created_by=admin,
            )
            QuestionOption.objects.bulk_create(
                [QuestionOption(question=q, text="True", is_correct=True, order=0), QuestionOption(question=q, text="False", is_correct=False, order=1)]
            )

        if not Exam.objects.filter(title="Maths Unit Test 1").exists():
            now = timezone.now()
            exam = Exam.objects.create(
                title="Maths Unit Test 1", school_class=cls8, subject=maths, instructions="Answer all questions. No calculators.",
                start_at=now - timedelta(minutes=5), end_at=now + timedelta(hours=8), duration_min=30,
                pass_marks=Decimal("3"), created_by=admin, settings={"access_code": ""},
            )
            exam.sections.set([sec_a, sec_b])
            ExamPart.objects.create(exam=exam, name="Part A", order=1, rule={"easy": 3, "medium": 2, "hard": 1, "chapters": []})
            generate(exam)
            schedule(exam)
        self.stdout.write(self.style.SUCCESS("Demo data: admin/admin-pass-123, students 8A01..8B06 / student-pass-123, live exam 'Maths Unit Test 1'."))
