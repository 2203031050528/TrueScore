from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.attempts.models import Attempt, AttemptAnswer
from apps.audit.models import AuditLog
from apps.exams.models import Exam
from conftest import Browser, build_exam, make_student

pytestmark = pytest.mark.django_db

EASY_ONLY = {"easy": 2}  # mcq1 (1 mark, -0.25) + mcq2 (1 mark) + tf in pool; fixed set of 2


def take(user, exam, answers):
    """Log in as `user`, answer {question: option_text} and submit. Returns attempt id."""
    b = Browser()
    b.login(user.username)
    paper = b.post(f"/api/v1/exams/{exam.pk}/start").json()
    for q in paper["questions"]:
        text = answers.get(q["text"])
        if text is not None:
            token = next(o["id"] for o in q["options"] if o["text"] == text)
            b.put(f"/api/v1/attempts/{paper['attempt_id']}/answers/{q['id']}", {"options": [token]})
    b.post(f"/api/v1/attempts/{paper['attempt_id']}/submit")
    return b, paper["attempt_id"]


def close(exam):
    Exam.objects.filter(pk=exam.pk).update(end_at=timezone.now() - timedelta(minutes=1))
    exam.refresh_from_db()


@pytest.fixture
def mcq_exam(structure, bank):
    return build_exam(structure, sections=("sec_8a", "sec_8b"), rule={"easy": 3}, pass_marks="2")


def test_results_are_403_until_published(admin_browser, student, mcq_exam):
    b, _ = take(student, mcq_exam, {"2+2?": "4", "3+3?": "6", "1 is prime": "False"})
    r = b.get(f"/api/v1/results/{mcq_exam.pk}")
    assert r.status_code == 403 and r.json()["code"] == "not_published"
    assert b.get("/api/v1/results").json() == []
    # Publishing while the window is open is refused.
    assert admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {}).status_code == 400
    close(mcq_exam)
    r = admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {"show_answers": True})
    assert r.status_code == 200, r.content
    detail = b.get(f"/api/v1/results/{mcq_exam.pk}").json()
    assert Decimal(detail["score"]) == 3 and detail["passed"] and detail["rank"] == 1
    assert detail["questions"][0]["explanation"].startswith("explain")
    assert any(o["is_correct"] for o in detail["questions"][0]["options"])


def test_publish_per_section(admin_browser, student, student_8b, mcq_exam, structure):
    b_a, _ = take(student, mcq_exam, {"2+2?": "4"})
    b_b, _ = take(student_8b, mcq_exam, {"2+2?": "4"})
    close(mcq_exam)
    admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {"section_ids": [structure["sec_8a"].pk]})
    assert b_a.get(f"/api/v1/results/{mcq_exam.pk}").status_code == 200
    assert b_b.get(f"/api/v1/results/{mcq_exam.pk}").status_code == 403
    mcq_exam.refresh_from_db()
    assert mcq_exam.status != "published"
    admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {"section_ids": [structure["sec_8b"].pk]})
    mcq_exam.refresh_from_db()
    assert mcq_exam.status == "published"


def test_rank_within_section_with_ties(admin_browser, structure, mcq_exam):
    users = [make_student(structure, f"8A{i:02d}") for i in range(50, 54)]
    answers = [
        {"2+2?": "4", "3+3?": "6", "1 is prime": "False"},  # 3
        {"2+2?": "4", "3+3?": "6"},  # 2
        {"2+2?": "4", "3+3?": "6"},  # 2
        {"2+2?": "5"},  # -0.25
    ]
    ids = [take(u, mcq_exam, a)[1] for u, a in zip(users, answers)]
    close(mcq_exam)
    admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {})
    ranks = [Attempt.objects.get(pk=i).rank for i in ids]
    assert ranks == [1, 2, 2, 4]


def test_show_answers_off_hides_review(admin_browser, student, mcq_exam):
    b, _ = take(student, mcq_exam, {"2+2?": "4"})
    close(mcq_exam)
    admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {"show_answers": False})
    detail = b.get(f"/api/v1/results/{mcq_exam.pk}").json()
    assert detail["questions"] is None and detail["score"] is not None


def test_regrade_after_key_fix_is_audited(admin_browser, student, mcq_exam, bank):
    b, aid = take(student, mcq_exam, {"2+2?": "5"})
    assert Attempt.objects.get(pk=aid).score == Decimal("-0.25")
    wrong_key = bank["mcq1"].options.get(text="5").pk
    r = admin_browser.post(
        f"/api/v1/admin/exams/{mcq_exam.pk}/regrade", {"question_id": bank["mcq1"].pk, "correct_option_ids": [wrong_key], "reason": "key typo"}
    )
    assert r.status_code == 200, r.content
    assert Attempt.objects.get(pk=aid).score == Decimal("1")
    log = AuditLog.objects.get(action="exam.regrade")
    assert log.reason == "key typo" and log.before["correct_option_ids"] != log.after["correct_option_ids"]
    assert admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/regrade", {"question_id": bank["mcq1"].pk}).status_code == 400  # no reason


def test_manual_marking_blocks_publish_until_done(admin_browser, student, structure, bank):
    exam = build_exam(structure, rule={"hard": 1}, pass_marks="1")
    b = Browser()
    b.login(student.username)
    paper = b.post(f"/api/v1/exams/{exam.pk}/start").json()
    b.put(f"/api/v1/attempts/{paper['attempt_id']}/answers/{bank['short'].pk}", {"text": "p over q"})
    b.post(f"/api/v1/attempts/{paper['attempt_id']}/submit")
    close(exam)
    assert admin_browser.post(f"/api/v1/admin/exams/{exam.pk}/publish", {}).status_code == 400
    queue = admin_browser.get(f"/api/v1/admin/exams/{exam.pk}/marking").json()
    assert queue["pending"] == 1
    answer_id = queue["results"][0]["answer_id"]
    assert admin_browser.post(f"/api/v1/admin/answers/{answer_id}/mark", {"marks_awarded": "9"}).status_code == 400
    r = admin_browser.post(f"/api/v1/admin/answers/{answer_id}/mark", {"marks_awarded": "2.5"})
    assert r.status_code == 200 and r.json()["grading_status"] == "graded"
    exam.refresh_from_db()
    assert exam.status == "graded"
    assert admin_browser.post(f"/api/v1/admin/exams/{exam.pk}/publish", {}).status_code == 200
    assert Decimal(b.get(f"/api/v1/results/{exam.pk}").json()["score"]) == Decimal("2.5")


def test_analytics(admin_browser, structure, mcq_exam, student, student2):
    take(student, mcq_exam, {"2+2?": "4", "3+3?": "6", "1 is prime": "False"})
    take(student2, mcq_exam, {"2+2?": "5"})
    data = admin_browser.get(f"/api/v1/admin/exams/{mcq_exam.pk}/analytics").json()
    assert data["submitted"] == 2 and data["pass_rate"] == 50.0
    assert Decimal(str(data["highest"])) == 3 and Decimal(str(data["lowest"])) == Decimal("-0.25")
    assert sum(b["count"] for b in data["distribution"]) == 2
    acc = {q["text"]: q["accuracy"] for q in data["per_question"]}
    assert acc["2+2?"] == 50.0 and acc["3+3?"] == 50.0


def test_progress_dashboard(admin_browser, student, mcq_exam):
    b, _ = take(student, mcq_exam, {"2+2?": "4"})
    close(mcq_exam)
    admin_browser.post(f"/api/v1/admin/exams/{mcq_exam.pk}/publish", {})
    data = b.get("/api/v1/me/progress").json()
    assert data["student"]["roll_no"] == student.username
    assert len(data["score_trend"]) == 1 and data["rank"]["rank"] == 1
    assert data["weak_chapters"][0]["chapter"] in {"Rational Numbers", "Linear Equations"}
    assert AttemptAnswer.objects.count() == 1
