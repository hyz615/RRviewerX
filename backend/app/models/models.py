from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from datetime import date


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str
    sub: str  # provider subject id
    email: Optional[str] = None
    disabled: bool = False
    ban_reason: Optional[str] = None
    ban_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LocalUser(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    password_hash: str
    is_admin: bool = False
    disabled: bool = False
    ban_reason: Optional[str] = None
    ban_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewSheet(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    source_id: Optional[int] = Field(default=None, index=True)
    kind: str  # outline|qa|flashcards
    content: str  # JSON string
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Vip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True, unique=True)
    is_vip: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UsageCounter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True)
    day: date = Field(index=True)
    count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MonthlyUsage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True)
    year: int = Field(index=True)
    month: int = Field(index=True)
    count: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Ticket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    subject: str
    content: str
    status: str = Field(default="open", index=True)  # open|in_progress|resolved|closed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TicketReply(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(index=True)
    author_id: Optional[int] = Field(default=None, index=True)
    author_role: str = Field(default="admin")  # admin|user
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
