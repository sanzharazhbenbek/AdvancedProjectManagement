from __future__ import annotations

import re
from datetime import datetime


ROLE_LABELS = {
    "admin": "Admin",
    "organizer": "Organizer",
    "user": "Member",
}

EVENT_STATUS_LABELS = {
    "upcoming": "Upcoming",
    "sold_out": "Sold out",
    "past": "Past",
    "cancelled": "Cancelled",
}

BOOKING_STATUS_LABELS = {
    "pending_payment": "Pending payment",
    "paid": "Paid",
    "cancelled": "Cancelled",
    "expired": "Expired",
}

TICKET_STATUS_LABELS = {
    "valid": "Valid",
    "used": "Used",
    "cancelled": "Cancelled",
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "event"


def format_kzt(amount: int | float) -> str:
    return f"{int(amount):,} KZT".replace(",", " ")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "Not available"
    return value.strftime("%d %b %Y, %H:%M")


def format_short_datetime(value: datetime | None) -> str:
    if value is None:
        return "Not available"
    return value.strftime("%d %b %H:%M")


def format_percent(value: float) -> str:
    return f"{value:.0%}"


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.title())


def mask_reference(value: str) -> str:
    if len(value) <= 6:
        return value
    return f"{value[:3]}•••{value[-3:]}"
