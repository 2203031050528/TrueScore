import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from conftest import PASSWORD, Browser, make_student

pytestmark = pytest.mark.django_db


def test_login_sets_httponly_cookies_and_no_tokens_in_body(student):
    b = Browser()
    r = b.login(student.username)
    assert r.json()["username"] == student.username
    assert "access" not in r.json() and "refresh" not in r.json()
    access = r.cookies[settings.AUTH_ACCESS_COOKIE]
    refresh = r.cookies[settings.AUTH_REFRESH_COOKIE]
    assert access["httponly"] and refresh["httponly"]
    assert access["samesite"] == "Lax"
    assert refresh["path"] == settings.AUTH_REFRESH_COOKIE_PATH
    assert r.cookies[settings.DEVICE_COOKIE]["httponly"]


def test_wrong_password_and_lockout(student):
    b = Browser()
    for _ in range(settings.LOGIN_MAX_FAILURES):
        r = b.post("/api/v1/auth/login", {"username": student.username, "password": "nope-nope"})
        assert r.status_code == 401
    r = b.post("/api/v1/auth/login", {"username": student.username, "password": PASSWORD})
    assert r.status_code == 429
    assert r.json()["code"] == "locked_out"


def test_unknown_user_gets_same_error(db):
    r = Browser().post("/api/v1/auth/login", {"username": "ghost", "password": "whatever1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid roll number or password."


def test_login_requires_csrf_token(student):
    client = APIClient(enforce_csrf_checks=True)
    r = client.post("/api/v1/auth/login", {"username": student.username, "password": PASSWORD}, format="json")
    assert r.status_code == 403


def test_state_changing_request_without_csrf_is_rejected(student_browser):
    token = student_browser.cookies["csrftoken"].value
    r = APIClient.post(student_browser, "/api/v1/auth/change-password", {"current_password": PASSWORD, "new_password": "brand-new-pass-9"}, format="json")
    assert r.status_code == 403
    assert token  # the cookie exists; only the header was missing


def test_bearer_header_is_not_accepted(student):
    from apps.accounts.tokens import tokens_for

    _, access = tokens_for(student)
    client = APIClient()
    r = client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert r.status_code == 401


def test_first_login_must_change_password(structure):
    user = make_student(structure, "8A09", must_change=True)
    b = Browser()
    b.login(user.username)
    assert b.get("/api/v1/me").json()["must_change_password"] is True
    r = b.get("/api/v1/videos")
    assert r.status_code == 403 and r.json()["code"] == "password_change_required"
    r = b.post("/api/v1/auth/change-password", {"current_password": PASSWORD, "new_password": "short"})
    assert r.status_code == 400
    r = b.post("/api/v1/auth/change-password", {"current_password": PASSWORD, "new_password": "a-much-better-pass-7"})
    assert r.status_code == 200, r.content
    assert b.get("/api/v1/videos").status_code == 200


def test_force_logout_revokes_existing_sessions(student, student_browser):
    assert student_browser.get("/api/v1/me").status_code == 200
    student.bump_token_version()
    assert student_browser.get("/api/v1/me").status_code == 401
    assert student_browser.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_rotates_and_blacklists(student):
    b = Browser()
    b.login(student.username)
    old_refresh = b.cookies[settings.AUTH_REFRESH_COOKIE].value
    r = b.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    assert b.cookies[settings.AUTH_REFRESH_COOKIE].value != old_refresh
    # Replaying the old refresh token fails: it was blacklisted on rotation.
    thief = Browser()
    thief.cookies[settings.AUTH_REFRESH_COOKIE] = old_refresh
    assert thief.post("/api/v1/auth/refresh").status_code == 401


def test_logout_blacklists_refresh(student):
    b = Browser()
    b.login(student.username)
    refresh = b.cookies[settings.AUTH_REFRESH_COOKIE].value
    assert b.post("/api/v1/auth/logout").status_code == 200
    replay = Browser()
    replay.cookies[settings.AUTH_REFRESH_COOKIE] = refresh
    assert replay.post("/api/v1/auth/refresh").status_code == 401


def test_suspended_user_is_locked_out(student, student_browser):
    User.objects.filter(pk=student.pk).update(is_active=False)
    assert student_browser.get("/api/v1/me").status_code == 401
    r = Browser().post("/api/v1/auth/login", {"username": student.username, "password": PASSWORD})
    assert r.status_code == 401


def test_change_password_logs_out_other_devices(student):
    a, b = Browser(), Browser()
    a.login(student.username)
    b.login(student.username)
    r = a.post("/api/v1/auth/change-password", {"current_password": PASSWORD, "new_password": "another-good-pass-3"})
    assert r.status_code == 200
    assert a.get("/api/v1/me").status_code == 200
    assert b.get("/api/v1/me").status_code == 401


def test_argon2_is_the_production_hasher():
    from config.settings import base

    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"
