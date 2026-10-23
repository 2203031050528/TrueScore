from datetime import timedelta

import pytest
from django.utils import timezone

from apps.videos.models import Video, WatchProgress
from conftest import Browser

pytestmark = pytest.mark.django_db


@pytest.fixture
def videos(structure, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "a.mp4").write_bytes(b"0123456789" * 10)
    return {
        "pub": Video.objects.create(chapter=structure["ch1"], title="Fractions", r2_key="videos/a.mp4", duration_s=100, status="published"),
        "draft": Video.objects.create(chapter=structure["ch1"], title="Draft", r2_key="videos/a.mp4", duration_s=100),
        "other": Video.objects.create(chapter=structure["ch9"], title="Class 9", r2_key="videos/a.mp4", duration_s=100, status="published"),
    }


def test_student_sees_only_own_class_published(student_browser, videos):
    titles = [v["title"] for v in student_browser.get("/api/v1/videos").json()]
    assert titles == ["Fractions"]
    assert student_browser.get(f"/api/v1/videos/{videos['draft'].pk}/play-url").status_code == 404
    assert student_browser.get(f"/api/v1/videos/{videos['other'].pk}/play-url").status_code == 404


def test_play_url_is_signed_and_streams_ranges(student_browser, videos):
    url = student_browser.get(f"/api/v1/videos/{videos['pub'].pk}/play-url").json()["url"]
    anon = Browser()
    r = anon.get(url, HTTP_RANGE="bytes=10-19")
    assert r.status_code == 206 and b"".join(r.streaming_content) == b"0123456789"
    assert r["Content-Range"] == "bytes 10-19/100"
    assert anon.get(url[:-3] + "xyz").status_code == 403  # tampered signature


def test_heartbeat_caps_credit_and_completes(student_browser, student, videos):
    vid = videos["pub"].pk
    r = student_browser.post(f"/api/v1/videos/{vid}/progress", {"position_s": 15, "delta_s": 3600}).json()
    assert r["seconds_watched"] <= 20  # one request cannot fake an hour
    # Rapid-fire heartbeats earn almost nothing.
    r = student_browser.post(f"/api/v1/videos/{vid}/progress", {"position_s": 30, "delta_s": 15}).json()
    assert r["seconds_watched"] <= 22
    # Simulate genuine watching: 15 s between beats.
    for i in range(10):
        WatchProgress.objects.filter(student=student, video_id=vid).update(updated_at=timezone.now() - timedelta(seconds=15))
        r = student_browser.post(f"/api/v1/videos/{vid}/progress", {"position_s": 30 + i * 15, "delta_s": 15}).json()
    assert r["completed"] is True and r["seconds_watched"] >= 90
    listed = student_browser.get("/api/v1/videos").json()[0]["progress"]
    assert listed["completed"] and listed["last_position_s"] == 100


def test_admin_upload_flow(admin_browser, structure, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    r = admin_browser.post("/api/v1/admin/videos/upload-url", {"kind": "videos", "content_type": "video/mp4", "size": 10})
    assert r.status_code == 200
    key, upload = r.json()["key"], r.json()["upload"]
    assert admin_browser.post("/api/v1/admin/videos", {"chapter": structure["ch1"].pk, "title": "T", "r2_key": key, "duration_s": 60}).status_code == 400
    put = Browser().generic("PUT", upload["url"], b"fakevideo!", content_type="video/mp4")
    assert put.status_code == 200
    r = admin_browser.post("/api/v1/admin/videos", {"chapter": structure["ch1"].pk, "title": "T", "r2_key": key, "duration_s": 60})
    assert r.status_code == 201, r.content
    bad = admin_browser.post("/api/v1/admin/videos/upload-url", {"kind": "videos", "content_type": "text/html", "size": 10})
    assert bad.status_code == 400
