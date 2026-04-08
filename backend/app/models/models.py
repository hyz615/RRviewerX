from typing import Optional
from datetime import datetime, date, timezone
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str
    sub: str  # provider subject id
    email: Optional[str] = None
    disabled: bool = False
    ban_reason: Optional[str] = None
    ban_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class LocalUser(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    password_hash: str
    is_admin: bool = False
    disabled: bool = False
    ban_reason: Optional[str] = None
    ban_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class Trial(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    client_fingerprint: str
    used: bool = False
    used_at: Optional[datetime] = None


class FileMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    filename: str
    content_type: Optional[str] = None
    size: int = 0
    stored_path: Optional[str] = None
    subject_code: Optional[str] = Field(default=None, index=True)
    course_name: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class Course(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "subject_code", "course_name", name="ux_course_user_subject_course"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    subject_code: Optional[str] = Field(default=None, index=True)
    course_name: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class CourseUnit(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="ux_courseunit_course_order"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(index=True, foreign_key="course.id")
    title: str
    order_index: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class CourseChapter(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("unit_id", "order_index", name="ux_coursechapter_unit_order"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(index=True, foreign_key="course.id")
    unit_id: int = Field(index=True, foreign_key="courseunit.id")
    title: str
    order_index: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class FileChapterMapping(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("file_id", "chapter_id", name="ux_filechaptermapping_file_chapter"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    file_id: int = Field(index=True, foreign_key="filemeta.id")
    chapter_id: int = Field(index=True, foreign_key="coursechapter.id")
    confidence: float = 0.0
    mapping_source: str = Field(default="auto")
    created_at: datetime = Field(default_factory=_utcnow)


class ReviewSheet(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    source_id: Optional[int] = Field(default=None, index=True)
    kind: str  # outline|qa|flashcards
    content: str  # JSON string
    subject_code: Optional[str] = Field(default=None, index=True)
    course_name: Optional[str] = Field(default=None, index=True)
    exam_type: Optional[str] = Field(default=None, index=True)
    exam_name: Optional[str] = None
    selected_chapter_ids: Optional[str] = None
    selected_chapter_labels: Optional[str] = None
    is_favorite: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)


class Vip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True, unique=True)
    is_vip: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class UsageCounter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True)
    day: date = Field(index=True)
    count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class MonthlyUsage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True)
    year: int = Field(index=True)
    month: int = Field(index=True)
    count: int = 0
    updated_at: datetime = Field(default_factory=_utcnow)


class Ticket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    subject: str
    content: str
    status: str = Field(default="open", index=True)  # open|in_progress|resolved|closed
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class TicketReply(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(index=True)
    author_id: Optional[int] = Field(default=None, index=True)
    author_role: str = Field(default="admin")  # admin|user
    content: str
    created_at: datetime = Field(default_factory=_utcnow)
