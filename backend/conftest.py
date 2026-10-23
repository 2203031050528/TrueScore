from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear, Chapter, SchoolClass, Section, Subject
from apps.accounts.models import StudentProfile, User
from apps.exams.models import Exam, ExamPart, Question, QuestionOption
from apps.exams.services import generate, schedule

PASSWORD = "correct-horse-42"


class Browser(APIClient):
    """APIClient that behaves like the real SPA: CSRF enforced, token echoed in X-CSRFToken."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, enforce_csrf_checks=True, **kwargs)
        self.get("/api/v1/auth/csrf")

    def _csrf(self, kwargs):
        token = self.cookies.get("csrftoken")
        if token is not None:
            kwargs.setdefault("HTTP_X_CSRFTOKEN", token.value)
        kwargs.setdefault("format", "json")
        return kwargs

    def post(self, path, data=None, **kwargs):
        return super().post(path, data, **self._csrf(kwargs))

    def put(self, path, data=None, **kwargs):
        return super().put(path, data, **self._csrf(kwargs))

    def patch(self, path, data=None, **kwargs):
        return super().patch(path, data, **self._csrf(kwargs))

    def delete(self, path, data=None, **kwargs):
        return super().delete(path, data, **self._csrf(kwargs))

    def login(self, username, password=PASSWORD):  # noqa: D102 - overrides Django's session login on purpose
        response = self.post("/api/v1/auth/login", {"username": username, "password": password})
        assert response.status_code == 200, response.content
        return response


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def structure(db):
    year = AcademicYear.objects.create(label="2026-27", is_current=True)
    cls8 = SchoolClass.objects.create(grade=8)
    cls9 = SchoolClass.objects.create(grade=9)
    sec_8a = Section.objects.create(school_class=cls8, name="A")
    sec_8b = Section.objects.create(school_class=cls8, name="B")
    sec_9a = Section.objects.create(school_class=cls9, name="A")
    maths = Subject.objects.create(school_class=cls8, name="Mathematics")
    science9 = Subject.objects.create(school_class=cls9, name="Science")
    ch1 = Chapter.objects.create(subject=maths, name="Rational Numbers", order=1)
    ch2 = Chapter.objects.create(subject=maths, name="Linear Equations", order=2)
    ch9 = Chapter.objects.create(subject=science9, name="Matter", order=1)
    return {
        "year": year, "cls8": cls8, "cls9": cls9, "sec_8a": sec_8a, "sec_8b": sec_8b, "sec_9a": sec_9a,
        "maths": maths, "science9": science9, "ch1": ch1, "ch2": ch2, "ch9": ch9,
    }


@pytest.fixture
def admin_user(db):
    user = User(username="admin", full_name="Admin", role=User.Role.ADMIN)
    user.set_password(PASSWORD)
    user.save()
    return user


def make_student(structure, roll, section_key="sec_8a", must_change=False):
    section = structure[section_key]
    user = User(username=roll, full_name=f"Student {roll}", role=User.Role.STUDENT, must_change_password=must_change)
    user.set_password(PASSWORD)
    user.save()
    StudentProfile.objects.create(user=user, academic_year=structure["year"], roll_no=roll, school_class=section.school_class, section=section)
    return user


@pytest.fixture
def student(structure):
    return make_student(structure, "8A01")


@pytest.fixture
def student2(structure):
    return make_student(structure, "8A02")


@pytest.fixture
def student_8b(structure):
    return make_student(structure, "8B01", "sec_8b")


@pytest.fixture
def student_9a(structure):
    return make_student(structure, "9A01", "sec_9a")


@pytest.fixture
def browser():
    return Browser()


@pytest.fixture
def admin_browser(admin_user):
    b = Browser()
    b.login("admin")
    return b


@pytest.fixture
def student_browser(student):
    b = Browser()
    b.login(student.username)
    return b


def add_mcq(subject, chapter, text, options, correct, difficulty="easy", marks="1", negative="0", qtype=Question.Type.MCQ_SINGLE):
    q = Question.objects.create(
        subject=subject, chapter=chapter, type=qtype, text=text, difficulty=difficulty,
        marks=Decimal(marks), negative_marks=Decimal(negative), explanation=f"explain {text}",
    )
    correct = correct if isinstance(correct, (list, tuple)) else [correct]
    QuestionOption.objects.bulk_create(
        [QuestionOption(question=q, text=t, is_correct=(i in correct), order=i) for i, t in enumerate(options)]
    )
    return q


@pytest.fixture
def bank(structure):
    s, c1, c2 = structure["maths"], structure["ch1"], structure["ch2"]
    qs = {
        "mcq1": add_mcq(s, c1, "2+2?", ["3", "4", "5"], 1, negative="0.25"),
        "mcq2": add_mcq(s, c1, "3+3?", ["6", "7", "8"], 0),
        "multi": add_mcq(s, c2, "Even numbers?", ["2", "3", "4", "5"], [0, 2], difficulty="medium", marks="2", qtype=Question.Type.MCQ_MULTI),
        "tf": add_mcq(s, c2, "1 is prime", ["True", "False"], 1, qtype=Question.Type.TRUE_FALSE),
    }
    qs["num"] = Question.objects.create(
        subject=s, chapter=c2, type=Question.Type.NUMERIC, text="Pi to 2dp", difficulty="medium",
        marks=Decimal("2"), numeric_answer=Decimal("3.14"), numeric_tolerance=Decimal("0.005"),
    )
    qs["short"] = Question.objects.create(
        subject=s, chapter=c1, type=Question.Type.SHORT_ANSWER, text="Define a rational number", difficulty="hard", marks=Decimal("3"),
    )
    return qs


def build_exam(structure, sections=("sec_8a",), start_offset=-5, end_offset=120, duration=30, rule=None, settings=None, do_schedule=True, pass_marks="3"):
    now = timezone.now()
    exam = Exam.objects.create(
        title="Unit Test",
        school_class=structure["cls8"],
        subject=structure["maths"],
        start_at=now + timedelta(minutes=start_offset),
        end_at=now + timedelta(minutes=end_offset),
        duration_min=duration,
        pass_marks=Decimal(pass_marks),
        settings=settings or {},
    )
    exam.sections.set([structure[s] for s in sections])
    ExamPart.objects.create(exam=exam, name="Part A", order=1, rule=rule or {"easy": 3, "medium": 2, "hard": 1})
    generate(exam)
    if do_schedule:
        # Scheduling validates the window is still open; build past windows by moving them afterwards.
        if exam.end_at <= now:
            Exam.objects.filter(pk=exam.pk).update(end_at=now + timedelta(minutes=1))
            exam.refresh_from_db()
        schedule(exam)
        Exam.objects.filter(pk=exam.pk).update(end_at=now + timedelta(minutes=end_offset))
        exam.refresh_from_db()
    return exam


@pytest.fixture
def live_exam(structure, bank):
    return build_exam(structure)
