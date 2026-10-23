from datetime import timedelta

import pytest
from django.utils import timezone

from apps.attempts.models import Attempt
from apps.exams.models import Exam, Question
from conftest import Browser, build_exam, make_student

pytestmark = pytest.mark.django_db


def test_create_exam_generate_and_schedule_via_api(admin_browser, structure, bank):
    now = timezone.now()
    r = admin_browser.post(
        "/api/v1/admin/exams",
        {
            "title": "API exam", "school_class": structure["cls8"].pk, "subject": structure["maths"].pk,
            "start_at": (now + timedelta(hours=1)).isoformat(), "end_at": (now + timedelta(hours=2)).isoformat(),
            "duration_min": 30, "pass_marks": "1", "section_ids": [structure["sec_8a"].pk],
        },
    )
    assert r.status_code == 201, r.content
    exam_id = r.json()["id"]
    part = admin_browser.post("/api/v1/admin/exam-parts", {"exam": exam_id, "name": "A", "rule": {"easy": 2, "medium": 1}})
    assert part.status_code == 201, part.content
    assert admin_browser.post(f"/api/v1/admin/exams/{exam_id}/generate", {}).status_code == 200
    r = admin_browser.post(f"/api/v1/admin/exams/{exam_id}/schedule")
    assert r.status_code == 200, r.content
    assert r.json()["status"] == "scheduled" and r.json()["effective_status"] == "upcoming"
    # Paper is locked now.
    assert admin_browser.patch(f"/api/v1/admin/exam-parts/{part.json()['id']}", {"name": "B"}).status_code == 400
    assert admin_browser.patch(f"/api/v1/admin/exams/{exam_id}", {"duration_min": 90}).status_code == 400
    assert admin_browser.patch(f"/api/v1/admin/exams/{exam_id}", {"title": "Renamed"}).status_code == 200
    assert admin_browser.post(f"/api/v1/admin/exams/{exam_id}/generate", {}).status_code == 400
    assert admin_browser.delete(f"/api/v1/admin/exams/{exam_id}").status_code == 400


def test_generator_reports_shortfall(admin_browser, structure, bank):
    now = timezone.now()
    exam = Exam.objects.create(title="x", school_class=structure["cls8"], subject=structure["maths"], start_at=now, end_at=now + timedelta(hours=1), duration_min=10)
    admin_browser.post("/api/v1/admin/exam-parts", {"exam": exam.pk, "name": "A", "rule": {"hard": 5}})
    r = admin_browser.post(f"/api/v1/admin/exams/{exam.pk}/generate", {})
    assert r.status_code == 400 and "5 hard needed, 1 available" in r.json()["detail"]


def test_sections_must_belong_to_exam_class(admin_browser, structure):
    now = timezone.now()
    r = admin_browser.post(
        "/api/v1/admin/exams",
        {
            "title": "x", "school_class": structure["cls8"].pk, "subject": structure["maths"].pk,
            "start_at": now.isoformat(), "end_at": (now + timedelta(hours=1)).isoformat(), "duration_min": 10,
            "section_ids": [structure["sec_9a"].pk],
        },
    )
    assert r.status_code == 400


def test_editing_a_used_question_creates_a_new_version(admin_browser, structure, bank, live_exam):
    q = bank["mcq1"]
    r = admin_browser.patch(f"/api/v1/admin/questions/{q.pk}", {"text": "2 + 2 = ?"})
    assert r.status_code == 201 and r.json()["versioned_from"] == q.pk
    q.refresh_from_db()
    assert q.text == "2+2?" and not q.is_active
    new = Question.objects.get(pk=r.json()["id"])
    assert new.version == 2 and new.parent_id == q.pk and new.options.count() == 3
    # The scheduled exam still points at the original.
    assert live_exam.exam_questions.filter(question=q).exists()


def test_editing_unused_question_is_in_place(admin_browser, bank):
    q = bank["mcq2"]
    r = admin_browser.patch(f"/api/v1/admin/questions/{q.pk}", {"text": "3 + 3 = ?"})
    assert r.status_code == 200 and r.json()["id"] == q.pk


def test_question_validation(admin_browser, structure):
    base = {"subject": structure["maths"].pk, "chapter": structure["ch1"].pk, "text": "q", "difficulty": "easy", "marks": "1"}
    two_correct = {**base, "type": "mcq_single", "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]}
    assert admin_browser.post("/api/v1/admin/questions", two_correct).status_code == 400
    numeric_no_key = {**base, "type": "numeric"}
    assert admin_browser.post("/api/v1/admin/questions", numeric_no_key).status_code == 400
    wrong_chapter = {**base, "chapter": structure["ch9"].pk, "type": "short_answer"}
    assert admin_browser.post("/api/v1/admin/questions", wrong_chapter).status_code == 400
    ok = {**base, "type": "mcq_multi", "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}, {"text": "c"}]}
    assert admin_browser.post("/api/v1/admin/questions", ok).status_code == 201


def test_question_csv_import(admin_browser, structure):
    import io

    csv = (
        "class,subject,chapter,type,difficulty,text,marks,options,correct,explanation\n"
        "8,Mathematics,Rational Numbers,mcq_single,easy,1+1?,1,1|2|3,B,two\n"
        "8,Mathematics,New Chapter,true_false,easy,Zero is even,1,,A,\n"
        "8,Mathematics,Rational Numbers,numeric,medium,10/4?,2,,2.5,\n"
    )
    f = io.BytesIO(csv.encode())
    f.name = "q.csv"
    r = admin_browser.post("/api/v1/admin/questions/import", {"file": f}, format="multipart")
    assert r.status_code == 201, r.content
    assert r.json()["created"] == 3
    assert Question.objects.get(text="1+1?").options.get(is_correct=True).text == "2"
    assert structure["maths"].chapters.filter(name="New Chapter").exists()


def test_per_student_random_sets(structure, bank):
    exam = build_exam(structure, rule={"easy": 1, "per_student": True}, pass_marks="0")
    assert exam.exam_questions.count() == 3  # whole easy pool is locked with the paper
    seen = set()
    for i in range(12):
        user = make_student(structure, f"8A{60 + i}")
        b = Browser()
        b.login(user.username)
        paper = b.post(f"/api/v1/exams/{exam.pk}/start").json()
        assert len(paper["questions"]) == 1
        seen.add(paper["questions"][0]["id"])
    assert len(seen) > 1
    assert all(a.max_score == 1 for a in Attempt.objects.filter(exam=exam))


def test_unschedule_only_before_attempts(admin_browser, student_browser, live_exam):
    student_browser.post(f"/api/v1/exams/{live_exam.pk}/start")
    assert admin_browser.post(f"/api/v1/admin/exams/{live_exam.pk}/unschedule").status_code == 400
