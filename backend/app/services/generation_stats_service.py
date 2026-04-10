from datetime import datetime, timezone
import zlib

from sqlalchemy import func
from sqlmodel import Session, select

from ..models.models import MonthlyUsage, ReviewSheet, SiteCounter


SITE_REVIEW_GENERATION_KEY = "review_generation_total"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_count(value: int | None) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _sum_rows(rows: list[MonthlyUsage] | list[SiteCounter]) -> int:
    return sum(_normalize_count(getattr(row, "count", 0)) for row in rows)


def _load_monthly_rows(session: Session, user_key: str, year: int, month: int) -> list[MonthlyUsage]:
    return session.exec(
        select(MonthlyUsage)
        .where(
            MonthlyUsage.user_key == user_key,
            MonthlyUsage.year == year,
            MonthlyUsage.month == month,
        )
        .order_by(MonthlyUsage.id)
    ).all()


def _load_site_rows(session: Session) -> list[SiteCounter]:
    return session.exec(
        select(SiteCounter)
        .where(SiteCounter.key == SITE_REVIEW_GENERATION_KEY)
        .order_by(SiteCounter.id)
    ).all()


def _count_review_sheets(
    session: Session,
    *,
    user_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> int:
    stmt = select(func.count()).select_from(ReviewSheet)
    if user_id is not None:
        stmt = stmt.where(ReviewSheet.user_id == user_id)
    if start_at is not None:
        stmt = stmt.where(ReviewSheet.created_at >= start_at)
    if end_at is not None:
        stmt = stmt.where(ReviewSheet.created_at < end_at)
    return _normalize_count(session.exec(stmt).one())


def _user_key_to_user_id(user_key: str | None) -> int | None:
    if not user_key:
        return None
    if user_key.startswith("local:"):
        try:
            return int(user_key.split(":", 1)[1])
        except Exception:
            return None
    subject = user_key.split(":", 1)[1] if ":" in user_key else user_key
    return zlib.adler32(subject.encode("utf-8")) & 0x7FFFFFFF


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _upsert_monthly_rows(
    session: Session,
    user_key: str,
    year: int,
    month: int,
    count: int,
    now: datetime,
) -> int:
    normalized = _normalize_count(count)
    rows = _load_monthly_rows(session, user_key, year, month)
    if rows:
        primary = rows[0]
        primary.count = normalized
        primary.updated_at = now
        session.add(primary)
        for duplicate in rows[1:]:
            session.delete(duplicate)
        return normalized

    session.add(
        MonthlyUsage(
            user_key=user_key,
            year=year,
            month=month,
            count=normalized,
            updated_at=now,
        )
    )
    return normalized


def _upsert_site_rows(session: Session, count: int, now: datetime) -> int:
    normalized = _normalize_count(count)
    rows = _load_site_rows(session)
    if rows:
        primary = rows[0]
        primary.count = normalized
        primary.updated_at = now
        session.add(primary)
        for duplicate in rows[1:]:
            session.delete(duplicate)
        return normalized

    session.add(
        SiteCounter(
            key=SITE_REVIEW_GENERATION_KEY,
            count=normalized,
            updated_at=now,
        )
    )
    return normalized


def get_monthly_generation_count(
    session: Session,
    user_key: str | None,
    *,
    year: int | None = None,
    month: int | None = None,
) -> int:
    if not user_key:
        return 0
    now = _utcnow()
    target_year = int(year or now.year)
    target_month = int(month or now.month)
    stored = _sum_rows(_load_monthly_rows(session, user_key, target_year, target_month))
    user_id = _user_key_to_user_id(user_key)
    if user_id is None:
        return stored
    start_at, end_at = _month_bounds(target_year, target_month)
    historical = _count_review_sheets(session, user_id=user_id, start_at=start_at, end_at=end_at)
    return max(stored, historical)


def set_monthly_generation_count(
    session: Session,
    user_key: str,
    count: int,
    *,
    year: int | None = None,
    month: int | None = None,
) -> int:
    now = _utcnow()
    target_year = int(year or now.year)
    target_month = int(month or now.month)
    return _upsert_monthly_rows(session, user_key, target_year, target_month, count, now)


def get_site_generation_total(session: Session) -> int:
    stored = _sum_rows(_load_site_rows(session))
    historical = _count_review_sheets(session)
    return max(stored, historical)


def record_review_generation(session: Session, user_key: str | None = None) -> dict[str, int]:
    now = _utcnow()
    site_total = _upsert_site_rows(session, get_site_generation_total(session) + 1, now)
    monthly_count = 0
    if user_key:
        monthly_count = _upsert_monthly_rows(
            session,
            user_key,
            now.year,
            now.month,
            get_monthly_generation_count(session, user_key, year=now.year, month=now.month) + 1,
            now,
        )
    return {
        "site_generation_total": site_total,
        "monthly_generation_count": monthly_count,
    }