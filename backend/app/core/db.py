from sqlmodel import SQLModel, create_engine, Session
from contextlib import contextmanager
from .config import settings


engine = create_engine(settings.DATABASE_URL, echo=False)


def _sqlite_ensure_columns() -> None:
    # Add missing columns for evolving models when using SQLite without Alembic
    url = str(settings.DATABASE_URL)
    if not url.startswith("sqlite"):
        return
    try:
        with engine.begin() as conn:
            # Check existing columns on localuser
            cols = set()
            res = conn.exec_driver_sql("PRAGMA table_info(localuser)")
            for row in res.fetchall():
                # row: (cid, name, type, notnull, dflt_value, pk)
                try:
                    cols.add(row[1])
                except Exception:
                    pass
            # Add columns if missing
            if "is_admin" not in cols:
                conn.exec_driver_sql("ALTER TABLE localuser ADD COLUMN is_admin INTEGER DEFAULT 0")
            if "disabled" not in cols:
                conn.exec_driver_sql("ALTER TABLE localuser ADD COLUMN disabled INTEGER DEFAULT 0")
            if "ban_reason" not in cols:
                conn.exec_driver_sql("ALTER TABLE localuser ADD COLUMN ban_reason TEXT")
            if "ban_expires_at" not in cols:
                conn.exec_driver_sql("ALTER TABLE localuser ADD COLUMN ban_expires_at TEXT")
            # For oauth user table
            cols_u = set()
            try:
                res2 = conn.exec_driver_sql("PRAGMA table_info(user)")
                for row in res2.fetchall():
                    try:
                        cols_u.add(row[1])
                    except Exception:
                        pass
                if "disabled" not in cols_u:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN disabled INTEGER DEFAULT 0")
                if "ban_reason" not in cols_u:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN ban_reason TEXT")
                if "ban_expires_at" not in cols_u:
                    conn.exec_driver_sql("ALTER TABLE user ADD COLUMN ban_expires_at TEXT")
            except Exception:
                pass
            # Ticket table: ensure columns exist if table exists
            try:
                res3 = conn.exec_driver_sql("PRAGMA table_info(ticket)")
                cols_t = {row[1] for row in res3.fetchall()}
                need_cols = {
                    "user_id": "INTEGER",
                    "subject": "TEXT",
                    "content": "TEXT",
                    "status": "TEXT",
                    "created_at": "TEXT",
                    "updated_at": "TEXT"
                }
                for name, typ in need_cols.items():
                    if name not in cols_t:
                        conn.exec_driver_sql(f"ALTER TABLE ticket ADD COLUMN {name} {typ}")
            except Exception:
                pass
            # TicketReply table columns
            try:
                res4 = conn.exec_driver_sql("PRAGMA table_info(ticketreply)")
                cols_r = {row[1] for row in res4.fetchall()}
                need_cols_r = {
                    "ticket_id": "INTEGER",
                    "author_id": "INTEGER",
                    "author_role": "TEXT",
                    "content": "TEXT",
                    "created_at": "TEXT",
                }
                for name, typ in need_cols_r.items():
                    if name not in cols_r:
                        conn.exec_driver_sql(f"ALTER TABLE ticketreply ADD COLUMN {name} {typ}")
            except Exception:
                pass
            # ReviewSheet table: ensure is_favorite column
            try:
                res5 = conn.exec_driver_sql("PRAGMA table_info(reviewsheet)")
                cols_rs = {row[1] for row in res5.fetchall()}
                if "is_favorite" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN is_favorite INTEGER DEFAULT 0")
                if "subject_code" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN subject_code TEXT")
                if "course_name" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN course_name TEXT")
                if "exam_type" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN exam_type TEXT")
                if "exam_name" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN exam_name TEXT")
                if "selected_chapter_ids" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN selected_chapter_ids TEXT")
                if "selected_chapter_labels" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN selected_chapter_labels TEXT")
                if "generation_mode" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN generation_mode TEXT")
                if "textbook_file_id" not in cols_rs:
                    conn.exec_driver_sql("ALTER TABLE reviewsheet ADD COLUMN textbook_file_id INTEGER")
            except Exception:
                pass
            # FileMeta table: ensure subject-mode columns
            try:
                res6 = conn.exec_driver_sql("PRAGMA table_info(filemeta)")
                cols_fm = {row[1] for row in res6.fetchall()}
                if "subject_code" not in cols_fm:
                    conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN subject_code TEXT")
                if "course_name" not in cols_fm:
                    conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN course_name TEXT")
                if "source_role" not in cols_fm:
                    conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN source_role TEXT DEFAULT 'material'")
            except Exception:
                pass
            # Course table: ensure textbook column exists
            try:
                res7 = conn.exec_driver_sql("PRAGMA table_info(course)")
                cols_course = {row[1] for row in res7.fetchall()}
                if "textbook_file_id" not in cols_course:
                    conn.exec_driver_sql("ALTER TABLE course ADD COLUMN textbook_file_id INTEGER")
            except Exception:
                pass
    except Exception:
        # best-effort; avoid blocking startup
        pass


def init_db() -> None:
    # Import models to register tables before create_all
    from ..models import models as _models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    _sqlite_ensure_columns()


def get_session():
    with Session(engine) as session:
        yield session
