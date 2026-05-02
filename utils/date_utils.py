from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.config import settings


def now_local() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone_name)).replace(tzinfo=None, second=0, microsecond=0)


def combine_date_and_time(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock).replace(second=0, microsecond=0)


def format_countdown(deadline: datetime | None) -> str:
    if deadline is None:
        return "No deadline"
    remaining = deadline - now_local()
    if remaining.total_seconds() <= 0:
        return "Expired"
    minutes = int(remaining.total_seconds() // 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h {mins}m left"
    return f"{mins}m left"


def days_from_now(days: int, hour: int, minute: int = 0) -> datetime:
    base = now_local() + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
