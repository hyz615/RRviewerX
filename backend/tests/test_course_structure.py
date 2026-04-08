import sys
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.core.jwt import sign_jwt
from app.main import app


def _auth_headers() -> dict[str, str]:
    token = sign_jwt("local:" + uuid4().hex, "local")
    return {"Authorization": f"Bearer {token}"}


def _course_payload(course_name: str, first_title: str, second_title: str) -> dict:
    return {
        "subject_code": "math",
        "course_name": course_name,
        "units": [
            {
                "title": "Unit 1",
                "chapters": [
                    {"title": first_title},
                    {"title": second_title},
                ],
            }
        ],
    }


def test_course_structure_roundtrip_and_manual_mapping():
    headers = _auth_headers()
    course_name = "Calculus-" + uuid4().hex[:8]

    with TestClient(app) as client:
        create = client.put(
            "/course-structure",
            headers=headers,
            json=_course_payload(course_name, "Limits", "Derivatives"),
        )
        assert create.status_code == 200
        course = create.json()["course"]
        assert course["course_name"] == course_name
        assert course["has_structure"] is True
        assert course["chapter_count"] == 2

        limits_id = next(
            chapter["id"]
            for unit in course["units"]
            for chapter in unit["chapters"]
            if chapter["title"] == "Limits"
        )
        derivatives_id = next(
            chapter["id"]
            for unit in course["units"]
            for chapter in unit["chapters"]
            if chapter["title"] == "Derivatives"
        )

        fetched = client.get(
            "/course-structure",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert fetched.status_code == 200
        assert fetched.json()["course"]["chapter_count"] == 2

        upload = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "math", "course_name": course_name},
            files={"file": ("limits_notes.txt", b"limits epsilon delta continuity", "text/plain")},
        )
        assert upload.status_code == 200
        upload_payload = upload.json()
        assert upload_payload["ok"] is True
        assert upload_payload["file_id"]
        assert any(match["chapter_id"] == limits_id for match in upload_payload["chapter_matches"])

        remap = client.put(
            f"/upload/{upload_payload['file_id']}/chapters",
            headers=headers,
            json={"chapter_ids": [derivatives_id]},
        )
        assert remap.status_code == 200
        remap_matches = remap.json()["chapter_matches"]
        assert [match["chapter_id"] for match in remap_matches] == [derivatives_id]
        assert all(match["mapping_source"] == "manual" for match in remap_matches)

        listing = client.get(
            "/upload/list",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert listing.status_code == 200
        listed_item = next(item for item in listing.json()["items"] if item["id"] == upload_payload["file_id"])
        assert [match["chapter_id"] for match in listed_item["chapter_matches"]] == [derivatives_id]


def test_ensure_course_persists_empty_course_in_listing():
    headers = _auth_headers()
    course_name = "Chemistry-" + uuid4().hex[:8]

    with TestClient(app) as client:
        ensure = client.post(
            "/course-structure/ensure",
            headers=headers,
            json={"subject_code": "chemistry", "course_name": course_name},
        )
        assert ensure.status_code == 200
        course = ensure.json()["course"]
        assert course["course_name"] == course_name
        assert course["has_structure"] is False
        assert course["chapter_count"] == 0

        listing = client.get("/course-structure/list", headers=headers)
        assert listing.status_code == 200
        assert any(
            item["course_name"] == course_name
            and item["subject_code"] == "chemistry"
            and item["source_count"] == 0
            for item in listing.json()["courses"]
        )


def test_generate_with_chapter_scope_persists_history_snapshot():
    headers = _auth_headers()
    course_name = "Linear-Algebra-" + uuid4().hex[:8]

    with TestClient(app) as client:
        create = client.put(
            "/course-structure",
            headers=headers,
            json=_course_payload(course_name, "Vectors", "Matrices"),
        )
        assert create.status_code == 200
        course = create.json()["course"]

        vectors_id = next(
            chapter["id"]
            for unit in course["units"]
            for chapter in unit["chapters"]
            if chapter["title"] == "Vectors"
        )
        matrices_id = next(
            chapter["id"]
            for unit in course["units"]
            for chapter in unit["chapters"]
            if chapter["title"] == "Matrices"
        )

        vector_upload = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "math", "course_name": course_name},
            files={"file": ("vectors_notes.txt", b"vectors basis span linear combination", "text/plain")},
        )
        assert vector_upload.status_code == 200
        vector_file_id = vector_upload.json()["file_id"]

        matrix_upload = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "math", "course_name": course_name},
            files={"file": ("matrices_notes.txt", b"matrices determinants inverses row operations", "text/plain")},
        )
        assert matrix_upload.status_code == 200
        matrix_file_id = matrix_upload.json()["file_id"]

        map_vectors = client.put(
            f"/upload/{vector_file_id}/chapters",
            headers=headers,
            json={"chapter_ids": [vectors_id]},
        )
        assert map_vectors.status_code == 200

        map_matrices = client.put(
            f"/upload/{matrix_file_id}/chapters",
            headers=headers,
            json={"chapter_ids": [matrices_id]},
        )
        assert map_matrices.status_code == 200

        generate = client.post(
            "/generate",
            headers=headers,
            json={
                "format": "qa",
                "length": "short",
                "subject_code": "math",
                "course_name": course_name,
                "exam_type": "final",
                "exam_name": "Scoped Final",
                "chapter_ids": [str(vectors_id)],
            },
        )
        assert generate.status_code == 200
        generate_payload = generate.json()
        assert generate_payload["ok"] is True
        assert generate_payload["selected_chapter_ids"] == [vectors_id]
        assert generate_payload["selected_chapter_labels"] == ["Unit 1 / Vectors"]

        detail = client.get(f"/history/{generate_payload['id']}", headers=headers)
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["subject_code"] == "math"
        assert detail_payload["course_name"] == course_name
        assert detail_payload["exam_type"] == "final"
        assert detail_payload["exam_name"] == "Scoped Final"
        assert detail_payload["selected_chapter_ids"] == [vectors_id]
        assert detail_payload["selected_chapter_labels"] == ["Unit 1 / Vectors"]

        listing = client.get(
            "/history",
            headers=headers,
            params={
                "subject_code": "math",
                "course_name": course_name,
                "exam_type": "final",
            },
        )
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert any(
            item["id"] == generate_payload["id"]
            and item["selected_chapter_ids"] == [vectors_id]
            and item["selected_chapter_labels"] == ["Unit 1 / Vectors"]
            for item in items
        )