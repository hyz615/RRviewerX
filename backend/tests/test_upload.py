import sys
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.core.jwt import sign_jwt


def test_upload_text_trial():
    with TestClient(app) as client:
        r = client.post("/upload", data={"text": "hello world"})
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["chars"] >= 5


def test_upload_list_filters_by_subject_context():
    token = sign_jwt("local:9201", "local")
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        first = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "math", "course_name": "Calculus I"},
            files={"file": ("calc.txt", b"limits and derivatives", "text/plain")},
        )
        assert first.status_code == 200
        assert first.json()["ok"] is True

        second = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "physics", "course_name": "Mechanics"},
            files={"file": ("mech.txt", b"force and acceleration", "text/plain")},
        )
        assert second.status_code == 200
        assert second.json()["ok"] is True

        filtered = client.get(
            "/upload/list",
            headers=headers,
            params={"subject_code": "math", "course_name": "Calculus I"},
        )
        assert filtered.status_code == 200
        items = filtered.json()["items"]
        assert len(items) >= 1
        assert all(item["subject_code"] == "math" for item in items)
        assert all(item["course_name"] == "Calculus I" for item in items)


def test_upload_creates_course_record_for_new_course_context():
    token = sign_jwt("local:9202", "local")
    headers = {"Authorization": f"Bearer {token}"}
    course_name = "Mechanics-" + uuid4().hex[:8]

    with TestClient(app) as client:
        upload = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "physics", "course_name": course_name},
            files={"file": ("mech.txt", b"force and acceleration", "text/plain")},
        )
        assert upload.status_code == 200
        assert upload.json()["ok"] is True

        listing = client.get("/course-structure/list", headers=headers)
        assert listing.status_code == 200
        assert any(
            item["course_name"] == course_name
            and item["subject_code"] == "physics"
            and item["source_count"] >= 1
            for item in listing.json()["courses"]
        )