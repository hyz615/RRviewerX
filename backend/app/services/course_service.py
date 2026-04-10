import json
from typing import Any, Iterable

from sqlmodel import Session, select

from ..models.models import Course, CourseUnit, CourseChapter, FileChapterMapping, FileMeta, ReviewSheet, CourseTextbookChapter


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_subject_code(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    return cleaned.lower() if cleaned else None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def format_chapter_label(unit_title: str | None, chapter_title: str) -> str:
    prefix = clean_optional_text(unit_title)
    if prefix:
        return f"{prefix} / {chapter_title}"
    return chapter_title


def serialize_textbook_meta(file_meta: FileMeta | None) -> dict[str, Any] | None:
    if file_meta is None or file_meta.id is None:
        return None
    return {
        "file_id": file_meta.id,
        "filename": file_meta.filename,
        "content_type": file_meta.content_type,
        "size": file_meta.size,
        "created_at": file_meta.created_at.isoformat() if file_meta.created_at else None,
    }


def get_course_textbook(session: Session, course: Course | None) -> FileMeta | None:
    if course is None or course.textbook_file_id is None:
        return None
    file_meta = session.get(FileMeta, course.textbook_file_id)
    if file_meta is None:
        return None
    return file_meta


def resolve_course(
    session: Session,
    user_id: int | None,
    subject_code: str | None,
    course_name: str | None,
    *,
    create_if_missing: bool = False,
) -> Course | None:
    normalized_subject_code = normalize_subject_code(subject_code)
    normalized_course_name = clean_optional_text(course_name)
    if user_id is None or not normalized_course_name:
        return None

    stmt = select(Course).where(Course.user_id == user_id)
    if normalized_subject_code:
        stmt = stmt.where(Course.subject_code == normalized_subject_code)
    else:
        stmt = stmt.where(Course.subject_code.is_(None))
    stmt = stmt.where(Course.course_name.ilike(normalized_course_name))
    course = session.exec(stmt).first()
    if course or not create_if_missing:
        return course

    course = Course(
        user_id=user_id,
        subject_code=normalized_subject_code,
        course_name=normalized_course_name,
    )
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


def _load_units(session: Session, course_id: int) -> list[CourseUnit]:
    return list(session.exec(
        select(CourseUnit)
        .where(CourseUnit.course_id == course_id)
        .order_by(CourseUnit.order_index.asc(), CourseUnit.id.asc())
    ).all())


def _load_chapters(session: Session, course_id: int) -> list[CourseChapter]:
    return list(session.exec(
        select(CourseChapter)
        .where(CourseChapter.course_id == course_id)
        .order_by(CourseChapter.unit_id.asc(), CourseChapter.order_index.asc(), CourseChapter.id.asc())
    ).all())


def serialize_course_structure(session: Session, course: Course | None) -> dict[str, Any] | None:
    if course is None:
        return None

    units = _load_units(session, course.id)
    chapters = _load_chapters(session, course.id)
    textbook = get_course_textbook(session, course)
    chapter_map: dict[int, list[CourseChapter]] = {}
    for chapter in chapters:
        chapter_map.setdefault(chapter.unit_id, []).append(chapter)

    serialized_units: list[dict[str, Any]] = []
    chapter_count = 0
    for unit in units:
        unit_chapters = chapter_map.get(unit.id, [])
        chapter_count += len(unit_chapters)
        serialized_units.append({
            "id": unit.id,
            "title": unit.title,
            "order_index": unit.order_index,
            "chapters": [
                {
                    "id": chapter.id,
                    "title": chapter.title,
                    "order_index": chapter.order_index,
                    "unit_id": chapter.unit_id,
                }
                for chapter in unit_chapters
            ],
        })

    return {
        "id": course.id,
        "subject_code": course.subject_code,
        "course_name": course.course_name,
        "textbook": serialize_textbook_meta(textbook),
        "unit_count": len(serialized_units),
        "chapter_count": chapter_count,
        "has_structure": chapter_count > 0,
        "units": serialized_units,
    }


def list_course_chapters(session: Session, course_id: int) -> list[dict[str, Any]]:
    units = _load_units(session, course_id)
    unit_map = {unit.id: unit for unit in units}
    chapters = _load_chapters(session, course_id)
    return [
        {
            "id": chapter.id,
            "course_id": chapter.course_id,
            "unit_id": chapter.unit_id,
            "unit_title": unit_map.get(chapter.unit_id).title if unit_map.get(chapter.unit_id) else None,
            "unit_order_index": unit_map.get(chapter.unit_id).order_index if unit_map.get(chapter.unit_id) else 0,
            "title": chapter.title,
            "order_index": chapter.order_index,
            "label": format_chapter_label(
                unit_map.get(chapter.unit_id).title if unit_map.get(chapter.unit_id) else None,
                chapter.title,
            ),
        }
        for chapter in chapters
    ]


def replace_course_structure(session: Session, course: Course, units_payload: Iterable[Any]) -> dict[str, Any]:
    existing_units = {unit.id: unit for unit in _load_units(session, course.id)}
    existing_chapters = {chapter.id: chapter for chapter in _load_chapters(session, course.id)}
    kept_unit_ids: set[int] = set()
    kept_chapter_ids: set[int] = set()

    for unit_index, raw_unit in enumerate(units_payload or []):
        unit_title = clean_optional_text((raw_unit or {}).get("title"))
        if not unit_title:
            continue

        incoming_unit_id = _coerce_int((raw_unit or {}).get("id"))
        unit = existing_units.get(incoming_unit_id) if incoming_unit_id in existing_units else None
        if unit is None:
            unit = CourseUnit(course_id=course.id, title=unit_title, order_index=unit_index)
            session.add(unit)
            session.flush()
        else:
            unit.title = unit_title
            unit.order_index = unit_index
            unit.course_id = course.id
            session.add(unit)
            session.flush()
        kept_unit_ids.add(unit.id)

        for chapter_index, raw_chapter in enumerate((raw_unit or {}).get("chapters") or []):
            chapter_title = clean_optional_text((raw_chapter or {}).get("title"))
            if not chapter_title:
                continue

            incoming_chapter_id = _coerce_int((raw_chapter or {}).get("id"))
            chapter = existing_chapters.get(incoming_chapter_id) if incoming_chapter_id in existing_chapters else None
            if chapter is None:
                chapter = CourseChapter(
                    course_id=course.id,
                    unit_id=unit.id,
                    title=chapter_title,
                    order_index=chapter_index,
                )
                session.add(chapter)
                session.flush()
            else:
                chapter.course_id = course.id
                chapter.unit_id = unit.id
                chapter.title = chapter_title
                chapter.order_index = chapter_index
                session.add(chapter)
                session.flush()
            kept_chapter_ids.add(chapter.id)

    removed_chapter_ids = [chapter_id for chapter_id in existing_chapters if chapter_id not in kept_chapter_ids]
    if removed_chapter_ids:
        removed_mappings = session.exec(
            select(FileChapterMapping).where(FileChapterMapping.chapter_id.in_(removed_chapter_ids))
        ).all()
        for mapping in removed_mappings:
            session.delete(mapping)
        removed_textbook_rows = session.exec(
            select(CourseTextbookChapter).where(CourseTextbookChapter.chapter_id.in_(removed_chapter_ids))
        ).all()
        for row in removed_textbook_rows:
            session.delete(row)
        for chapter_id in removed_chapter_ids:
            session.delete(existing_chapters[chapter_id])

    for unit_id, unit in existing_units.items():
        if unit_id not in kept_unit_ids:
            session.delete(unit)

    session.commit()
    return serialize_course_structure(session, course) or {
        "id": course.id,
        "subject_code": course.subject_code,
        "course_name": course.course_name,
        "unit_count": 0,
        "chapter_count": 0,
        "has_structure": False,
        "units": [],
    }


def _apply_course_scope_filters(
    stmt: Any,
    subject_field: Any,
    course_field: Any,
    subject_code: str | None,
    course_name: str | None,
) -> Any:
    normalized_subject_code = normalize_subject_code(subject_code)
    normalized_course_name = clean_optional_text(course_name)
    if not normalized_course_name:
        raise ValueError("course_name is required")

    if normalized_subject_code:
        stmt = stmt.where(subject_field == normalized_subject_code)
    else:
        stmt = stmt.where(subject_field.is_(None))
    return stmt.where(course_field.ilike(normalized_course_name))


def delete_course_bundle(
    session: Session,
    user_id: int | None,
    subject_code: str | None,
    course_name: str | None,
) -> dict[str, Any] | None:
    normalized_subject_code = normalize_subject_code(subject_code)
    normalized_course_name = clean_optional_text(course_name)
    if user_id is None or not normalized_course_name:
        raise ValueError("course_name is required")

    course = resolve_course(
        session,
        user_id,
        normalized_subject_code,
        normalized_course_name,
        create_if_missing=False,
    )

    file_rows = list(session.exec(
        _apply_course_scope_filters(
            select(FileMeta).where(FileMeta.user_id == user_id),
            FileMeta.subject_code,
            FileMeta.course_name,
            normalized_subject_code,
            normalized_course_name,
        )
    ).all())
    review_rows = list(session.exec(
        _apply_course_scope_filters(
            select(ReviewSheet).where(ReviewSheet.user_id == user_id),
            ReviewSheet.subject_code,
            ReviewSheet.course_name,
            normalized_subject_code,
            normalized_course_name,
        )
    ).all())

    unit_rows: list[CourseUnit] = []
    chapter_rows: list[CourseChapter] = []
    textbook_rows: list[CourseTextbookChapter] = []
    if course is not None and course.id is not None:
        unit_rows = _load_units(session, course.id)
        chapter_rows = _load_chapters(session, course.id)
        textbook_rows = list(session.exec(
            select(CourseTextbookChapter).where(CourseTextbookChapter.course_id == course.id)
        ).all())

    if course is None and not file_rows and not review_rows and not unit_rows and not chapter_rows and not textbook_rows:
        return None

    file_ids = [row.id for row in file_rows if row.id is not None]
    chapter_ids = [row.id for row in chapter_rows if row.id is not None]
    stored_paths = [row.stored_path for row in file_rows if row.stored_path]

    delete_file_mappings_for_files(session, file_ids)
    if chapter_ids:
        chapter_mappings = session.exec(
            select(FileChapterMapping).where(FileChapterMapping.chapter_id.in_(chapter_ids))
        ).all()
        for mapping in chapter_mappings:
            session.delete(mapping)

    for textbook_row in textbook_rows:
        session.delete(textbook_row)

    for review in review_rows:
        session.delete(review)
    for chapter in chapter_rows:
        session.delete(chapter)
    for unit in unit_rows:
        session.delete(unit)
    for file_row in file_rows:
        session.delete(file_row)
    if course is not None:
        session.delete(course)

    session.commit()
    return {
        "subject_code": normalized_subject_code,
        "course_name": normalized_course_name,
        "removed_course": bool(course is not None),
        "removed_file_count": len(file_rows),
        "removed_review_count": len(review_rows),
        "removed_unit_count": len(unit_rows),
        "removed_chapter_count": len(chapter_rows),
        "stored_paths": stored_paths,
    }


def list_file_chapter_mappings(session: Session, file_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
    normalized_ids = [file_id for file_id in {_coerce_int(value) for value in file_ids} if file_id is not None]
    if not normalized_ids:
        return {}

    mappings = list(session.exec(
        select(FileChapterMapping)
        .where(FileChapterMapping.file_id.in_(normalized_ids))
        .order_by(FileChapterMapping.file_id.asc(), FileChapterMapping.created_at.asc())
    ).all())
    if not mappings:
        return {}

    chapter_ids = [mapping.chapter_id for mapping in mappings]
    chapters = list(session.exec(select(CourseChapter).where(CourseChapter.id.in_(chapter_ids))).all())
    chapter_map = {chapter.id: chapter for chapter in chapters}
    unit_ids = [chapter.unit_id for chapter in chapters]
    units = list(session.exec(select(CourseUnit).where(CourseUnit.id.in_(unit_ids))).all()) if unit_ids else []
    unit_map = {unit.id: unit for unit in units}

    grouped: dict[int, list[dict[str, Any]]] = {}
    for mapping in mappings:
        chapter = chapter_map.get(mapping.chapter_id)
        if chapter is None:
            continue
        unit = unit_map.get(chapter.unit_id)
        grouped.setdefault(mapping.file_id, []).append({
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "unit_id": chapter.unit_id,
            "unit_title": unit.title if unit else None,
            "confidence": round(float(mapping.confidence or 0.0), 4),
            "mapping_source": mapping.mapping_source,
            "label": format_chapter_label(unit.title if unit else None, chapter.title),
            "_unit_order": unit.order_index if unit else 0,
            "_chapter_order": chapter.order_index,
        })

    for file_id, items in grouped.items():
        items.sort(key=lambda item: (item["_unit_order"], item["_chapter_order"], item["chapter_id"]))
        grouped[file_id] = [
            {
                "chapter_id": item["chapter_id"],
                "chapter_title": item["chapter_title"],
                "unit_id": item["unit_id"],
                "unit_title": item["unit_title"],
                "confidence": item["confidence"],
                "mapping_source": item["mapping_source"],
                "label": item["label"],
            }
            for item in items
        ]

    return grouped


def delete_file_mappings_for_files(session: Session, file_ids: Iterable[int]) -> None:
    normalized_ids = [file_id for file_id in {_coerce_int(value) for value in file_ids} if file_id is not None]
    if not normalized_ids:
        return

    mappings = session.exec(select(FileChapterMapping).where(FileChapterMapping.file_id.in_(normalized_ids))).all()
    for mapping in mappings:
        session.delete(mapping)


def replace_file_chapter_mappings(
    session: Session,
    user_id: int,
    file_id: int,
    chapter_ids: Iterable[int],
    *,
    mapping_source: str = "manual",
    confidence_map: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    file_meta = session.get(FileMeta, file_id)
    if file_meta is None or file_meta.user_id != user_id:
        raise ValueError("File not found")

    existing = session.exec(select(FileChapterMapping).where(FileChapterMapping.file_id == file_id)).all()
    for mapping in existing:
        session.delete(mapping)

    normalized_ids = [chapter_id for chapter_id in {_coerce_int(value) for value in chapter_ids} if chapter_id is not None]
    if not normalized_ids:
        session.commit()
        return []

    chapters = list(session.exec(select(CourseChapter).where(CourseChapter.id.in_(normalized_ids))).all())
    if not chapters:
        session.commit()
        return []

    file_course = resolve_course(session, user_id, file_meta.subject_code, file_meta.course_name, create_if_missing=False)
    if file_course is None:
        session.commit()
        return []

    chapters = [chapter for chapter in chapters if chapter.course_id == file_course.id]
    for chapter in chapters:
        session.add(FileChapterMapping(
            user_id=user_id,
            file_id=file_id,
            chapter_id=chapter.id,
            confidence=float((confidence_map or {}).get(chapter.id, 1.0 if mapping_source == "manual" else 0.0)),
            mapping_source=mapping_source,
        ))
    session.commit()
    return list_file_chapter_mappings(session, [file_id]).get(file_id, [])


def resolve_files_for_chapters(
    session: Session,
    user_id: int,
    chapter_ids: Iterable[int],
) -> tuple[list[int], list[int], list[str]]:
    normalized_ids: list[int] = []
    seen_ids: set[int] = set()
    for raw_id in chapter_ids:
        chapter_id = _coerce_int(raw_id)
        if chapter_id is None or chapter_id in seen_ids:
            continue
        seen_ids.add(chapter_id)
        normalized_ids.append(chapter_id)
    if not normalized_ids:
        return [], [], []

    mappings = list(session.exec(
        select(FileChapterMapping)
        .where(FileChapterMapping.user_id == user_id, FileChapterMapping.chapter_id.in_(normalized_ids))
        .order_by(FileChapterMapping.created_at.asc(), FileChapterMapping.id.asc())
    ).all())
    file_ids: list[int] = []
    file_seen: set[int] = set()
    for mapping in mappings:
        if mapping.file_id in file_seen:
            continue
        file_seen.add(mapping.file_id)
        file_ids.append(mapping.file_id)

    chapters = list(session.exec(select(CourseChapter).where(CourseChapter.id.in_(normalized_ids))).all())
    chapter_map = {chapter.id: chapter for chapter in chapters}
    unit_ids = [chapter.unit_id for chapter in chapters]
    units = list(session.exec(select(CourseUnit).where(CourseUnit.id.in_(unit_ids))).all()) if unit_ids else []
    unit_map = {unit.id: unit for unit in units}
    labels: list[str] = []
    for chapter_id in normalized_ids:
        chapter = chapter_map.get(chapter_id)
        if chapter is None:
            continue
        unit = unit_map.get(chapter.unit_id)
        labels.append(format_chapter_label(unit.title if unit else None, chapter.title))
    return file_ids, normalized_ids, labels


def delete_course_textbook_chapters(session: Session, course_id: int) -> None:
    rows = session.exec(
        select(CourseTextbookChapter).where(CourseTextbookChapter.course_id == course_id)
    ).all()
    for row in rows:
        session.delete(row)


def list_course_textbook_chapters(
    session: Session,
    textbook_file_id: int,
    chapter_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    stmt = select(CourseTextbookChapter).where(CourseTextbookChapter.textbook_file_id == textbook_file_id)
    normalized_ids = [chapter_id for chapter_id in {_coerce_int(value) for value in chapter_ids or []} if chapter_id is not None]
    if normalized_ids:
        stmt = stmt.where(CourseTextbookChapter.chapter_id.in_(normalized_ids))
    rows = list(session.exec(stmt.order_by(CourseTextbookChapter.order_index.asc(), CourseTextbookChapter.id.asc())).all())
    if not rows:
        return []

    chapter_map = {
        chapter.id: chapter
        for chapter in session.exec(
            select(CourseChapter).where(CourseChapter.id.in_([row.chapter_id for row in rows]))
        ).all()
    }
    unit_ids = [chapter.unit_id for chapter in chapter_map.values()]
    unit_map = {
        unit.id: unit
        for unit in session.exec(select(CourseUnit).where(CourseUnit.id.in_(unit_ids))).all()
    } if unit_ids else {}

    return [
        {
            "chapter_id": row.chapter_id,
            "chapter_title": chapter_map[row.chapter_id].title,
            "unit_id": chapter_map[row.chapter_id].unit_id,
            "unit_title": unit_map.get(chapter_map[row.chapter_id].unit_id).title if unit_map.get(chapter_map[row.chapter_id].unit_id) else None,
            "label": format_chapter_label(
                unit_map.get(chapter_map[row.chapter_id].unit_id).title if unit_map.get(chapter_map[row.chapter_id].unit_id) else None,
                chapter_map[row.chapter_id].title,
            ),
            "content": row.content,
            "order_index": row.order_index,
        }
        for row in rows
        if row.chapter_id in chapter_map
    ]


def replace_course_textbook_chapters(
    session: Session,
    course: Course,
    textbook_file_id: int,
    chapter_contents: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    delete_course_textbook_chapters(session, course.id)

    for index, item in enumerate(chapter_contents or []):
        chapter_id = _coerce_int((item or {}).get("chapter_id"))
        content = str((item or {}).get("content") or "").strip()
        if chapter_id is None or not content:
            continue
        session.add(CourseTextbookChapter(
            course_id=course.id,
            textbook_file_id=textbook_file_id,
            chapter_id=chapter_id,
            content=content,
            order_index=index,
        ))
    session.commit()
    return list_course_textbook_chapters(session, textbook_file_id)


def dump_json_list(values: Iterable[Any]) -> str | None:
    normalized = [value for value in values if value not in (None, "")]
    if not normalized:
        return None
    return json.dumps(normalized, ensure_ascii=False)


def load_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except Exception:
        return []
    return loaded if isinstance(loaded, list) else []