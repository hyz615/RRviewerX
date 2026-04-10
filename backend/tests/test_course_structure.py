import sys
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.core.db import engine
from app.core.jwt import sign_jwt
from app.main import app
from app.models.models import Course, CourseChapter, CourseUnit, FileChapterMapping, FileMeta, ReviewSheet
from app.routes import generate as generate_route


def _auth_headers() -> dict[str, str]:
    token = sign_jwt("local:" + uuid4().hex, "local")
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_for_user(user_id: int) -> dict[str, str]:
    token = sign_jwt(f"local:{user_id}", "local")
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


def test_delete_course_removes_related_data_and_files():
    user_id = 830001
    headers = _auth_headers_for_user(user_id)
    course_name = "Delete-Me-" + uuid4().hex[:8]

    with TestClient(app) as client:
        create = client.put(
            "/course-structure",
            headers=headers,
            json=_course_payload(course_name, "Limits", "Derivatives"),
        )
        assert create.status_code == 200
        course_id = create.json()["course"]["id"]

        upload = client.post(
            "/upload",
            headers=headers,
            data={"subject_code": "math", "course_name": course_name},
            files={"file": ("delete_me_notes.txt", b"limits epsilon delta continuity", "text/plain")},
        )
        assert upload.status_code == 200
        upload_payload = upload.json()
        file_id = upload_payload["file_id"]

        with Session(engine) as session:
            file_meta = session.get(FileMeta, file_id)
            assert file_meta is not None
            stored_path = Path(file_meta.stored_path)
            assert stored_path.exists()

            review = ReviewSheet(
                user_id=user_id,
                source_id=file_id,
                kind="qa",
                content="review payload",
                subject_code="math",
                course_name=course_name,
            )
            session.add(review)
            session.commit()

        delete = client.delete(
            "/course-structure",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert delete.status_code == 200
        delete_payload = delete.json()
        assert delete_payload["ok"] is True
        assert delete_payload["removed_course"] is True
        assert delete_payload["removed_file_count"] == 1
        assert delete_payload["removed_review_count"] == 1
        assert delete_payload["removed_unit_count"] == 1
        assert delete_payload["removed_chapter_count"] == 2
        assert delete_payload["removed_stored_file_count"] == 1

        listing = client.get("/course-structure/list", headers=headers)
        assert listing.status_code == 200
        assert not any(item["course_name"] == course_name for item in listing.json()["courses"])

        structure = client.get(
            "/course-structure",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert structure.status_code == 200
        assert structure.json()["course"] is None

        file_listing = client.get(
            "/upload/list",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert file_listing.status_code == 200
        assert file_listing.json()["items"] == []

        history_listing = client.get(
            "/history",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert history_listing.status_code == 200
        assert history_listing.json()["items"] == []

        with Session(engine) as session:
            assert session.exec(
                select(Course).where(Course.user_id == user_id, Course.course_name == course_name)
            ).first() is None
            assert session.exec(
                select(FileMeta).where(FileMeta.user_id == user_id, FileMeta.course_name == course_name)
            ).first() is None
            assert session.exec(
                select(ReviewSheet).where(ReviewSheet.user_id == user_id, ReviewSheet.course_name == course_name)
            ).first() is None
            assert session.exec(
                select(CourseUnit).where(CourseUnit.course_id == course_id)
            ).first() is None
            assert session.exec(
                select(CourseChapter).where(CourseChapter.course_id == course_id)
            ).first() is None
            assert session.exec(select(FileChapterMapping).where(FileChapterMapping.file_id == file_id)).first() is None

        assert not stored_path.exists()


def test_upload_textbook_auto_generates_structure_and_stays_out_of_material_library():
    headers = _auth_headers()
    course_name = "Textbook-" + uuid4().hex[:8]
    textbook_body = (
        b"Chapter 1 Limits\n"
        b"epsilon delta continuity\n\n"
        b"Chapter 2 Derivatives\n"
        b"slope tangent rate of change\n"
    )

    with TestClient(app) as client:
        upload = client.post(
            "/course-structure/textbook",
            headers=headers,
            data={"subject_code": "math", "course_name": course_name},
            files={"file": ("calc_textbook.txt", textbook_body, "text/plain")},
        )
        assert upload.status_code == 200
        payload = upload.json()
        assert payload["ok"] is True
        assert payload["course"]["textbook"]["filename"] == "calc_textbook.txt"
        assert payload["course"]["chapter_count"] == 2
        assert [
            chapter["title"]
            for unit in payload["course"]["units"]
            for chapter in unit["chapters"]
        ] == ["Limits", "Derivatives"]

        listing = client.get(
            "/upload/list",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert listing.status_code == 200
        assert listing.json()["items"] == []

        detach = client.delete(
            "/course-structure/textbook",
            headers=headers,
            params={"subject_code": "math", "course_name": course_name},
        )
        assert detach.status_code == 200
        assert detach.json()["course"]["textbook"] is None


def test_generate_supports_textbook_only_and_combined_modes(monkeypatch):
    headers = _auth_headers()
    course_name = "Textbook-Generate-" + uuid4().hex[:8]
    textbook_body = (
        b"Chapter 1 Limits\n"
        b"epsilon delta continuity\n\n"
        b"Chapter 2 Derivatives\n"
        b"slope tangent rate of change\n"
    )
    captured_inputs: list[str] = []

    def fake_generate_review(text: str, fmt: str, lang: str = "zh", length: str = "short") -> dict:
        captured_inputs.append(text)
        return {"pairs": [{"q": "What?", "a": "Answer."}]}

    monkeypatch.setattr(generate_route, "generate_review", fake_generate_review)

    with TestClient(app) as client:
        upload = client.post(
            "/course-structure/textbook",
            headers=headers,
            data={"subject_code": "math", "course_name": course_name},
            files={"file": ("calc_textbook.txt", textbook_body, "text/plain")},
        )
        assert upload.status_code == 200
        course = upload.json()["course"]
        limits_id = next(
            chapter["id"]
            for unit in course["units"]
            for chapter in unit["chapters"]
            if chapter["title"] == "Limits"
        )

        textbook_only = client.post(
            "/generate",
            headers=headers,
            json={
                "format": "qa",
                "length": "short",
                "subject_code": "math",
                "course_name": course_name,
                "chapter_ids": [str(limits_id)],
                "generation_mode": "textbook",
            },
        )
        assert textbook_only.status_code == 200
        textbook_payload = textbook_only.json()
        assert textbook_payload["ok"] is True
        assert textbook_payload["generation_mode"] == "textbook"
        assert "epsilon delta continuity" in captured_inputs[-1]
        assert "slope tangent rate of change" not in captured_inputs[-1]

        combined = client.post(
            "/generate",
            headers=headers,
            json={
                "format": "qa",
                "length": "short",
                "subject_code": "math",
                "course_name": course_name,
                "chapter_ids": [str(limits_id)],
                "generation_mode": "combined",
                "text": "focus on common exam traps",
            },
        )
        assert combined.status_code == 200
        combined_payload = combined.json()
        assert combined_payload["ok"] is True
        assert combined_payload["generation_mode"] == "combined"
        assert "epsilon delta continuity" in captured_inputs[-1]
        assert "focus on common exam traps" in captured_inputs[-1]

        detail = client.get(f"/history/{combined_payload['id']}", headers=headers)
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["generation_mode"] == "combined"
        assert detail_payload["textbook_file_id"] is not None
        assert detail_payload["textbook_name"] == "calc_textbook.txt"
