import io

import pytest

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.accounts.models import StudentProfile, User
from apps.audit.models import AuditLog
from conftest import Browser, make_student

pytestmark = pytest.mark.django_db


def _csv(text):
    f = io.BytesIO(text.encode())
    f.name = "students.csv"
    return f


def test_students_cannot_reach_admin_api(student_browser):
    for path in ["/api/v1/admin/students", "/api/v1/admin/exams", "/api/v1/admin/audit", "/api/v1/admin/questions"]:
        assert student_browser.get(path).status_code == 403


def test_anonymous_cannot_reach_api(db):
    assert Browser().get("/api/v1/admin/students").status_code == 401
    assert Browser().get("/api/v1/videos").status_code == 401


def test_csv_import_creates_students_with_one_time_passwords(admin_browser, structure):
    csv = "roll_no,name,class,section,guardian_phone\n8A10,Asha,8,A,999\n8C01,Ravi,8,C,\n"
    r = admin_browser.post("/api/v1/admin/students/import", {"file": _csv(csv)}, format="multipart")
    assert r.status_code == 201, r.content
    body = r.json()
    assert {row["roll_no"] for row in body["created"]} == {"8A10", "8C01"}
    assert body["sections_created"] == ["8-C"]
    user = User.objects.get(username="8A10")
    assert user.must_change_password and user.check_password(body["created"][0]["password"])
    assert AuditLog.objects.filter(action="student.import").exists()


def test_csv_import_is_all_or_nothing(admin_browser, structure):
    csv = "roll_no,name,class,section\n8A11,Good,8,A\n8A11,Dupe,8,A\n,NoRoll,8,A\n9X1,Bad,13,A\n"
    r = admin_browser.post("/api/v1/admin/students/import", {"file": _csv(csv)}, format="multipart")
    assert r.status_code == 400
    assert len(r.json()["errors"]) == 3
    assert not User.objects.filter(username="8A11").exists()


def test_create_reset_suspend_flow(admin_browser, structure):
    r = admin_browser.post("/api/v1/admin/students", {"roll_no": "8B20", "full_name": "Neha", "section_id": structure["sec_8b"].pk})
    assert r.status_code == 201, r.content
    sid, first_pw = r.json()["id"], r.json()["initial_password"]
    s = Browser()
    s.login("8B20", first_pw)

    r = admin_browser.post(f"/api/v1/admin/students/{sid}/reset-password", {"reason": "forgot"})
    new_pw = r.json()["initial_password"]
    assert s.get("/api/v1/me").status_code == 401  # old session revoked
    Browser().login("8B20", new_pw)

    admin_browser.post(f"/api/v1/admin/students/{sid}/suspend", {"reason": "left school"})
    assert Browser().post("/api/v1/auth/login", {"username": "8B20", "password": new_pw}).status_code == 401
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"student.create", "student.reset_password", "student.suspend"} <= actions


def test_duplicate_roll_number_rejected(admin_browser, structure, student):
    r = admin_browser.post("/api/v1/admin/students", {"roll_no": student.username, "full_name": "X", "section_id": structure["sec_8a"].pk})
    assert r.status_code == 400


def test_year_end_promotion(admin_browser, structure):
    cls12 = SchoolClass.objects.create(grade=12)
    sec12 = Section.objects.create(school_class=cls12, name="A")
    structure["sec_12a"] = sec12
    s8 = make_student(structure, "8A30")
    s12 = make_student(structure, "12A01", "sec_12a")
    r = admin_browser.post("/api/v1/admin/promote", {"new_year_label": "2027-28", "reason": "year end"})
    assert r.status_code == 200, r.content
    assert r.json()["promoted"] == 1 and r.json()["graduated"] == 1
    p = StudentProfile.objects.get(user=s8)
    assert p.school_class.grade == 9 and p.section.name == "A" and p.academic_year.label == "2027-28"
    s12.refresh_from_db()
    assert not s12.is_active
    assert AcademicYear.current().label == "2027-28"


def test_audit_log_is_append_only(admin_user):
    entry = AuditLog.objects.create(actor=admin_user, action="x", entity="y")
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
