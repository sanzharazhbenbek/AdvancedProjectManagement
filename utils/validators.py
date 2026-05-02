from __future__ import annotations

from datetime import datetime
from typing import Any

from core.security import normalize_email
from utils.formatters import slugify


CATEGORY_OPTIONS = [
    "Technology",
    "Business",
    "Conference",
    "Workshop",
    "Music",
    "University Club",
    "Community",
]

CITY_OPTIONS = ["Almaty", "Astana", "Shymkent", "Karaganda", "Atyrau"]


def validate_registration(full_name: str, email: str, password: str, confirm_password: str, role: str) -> list[str]:
    errors: list[str] = []
    if len(full_name.strip()) < 3:
        errors.append("Full name must contain at least 3 characters.")
    normalized_email = normalize_email(email)
    if "@" not in normalized_email or "." not in normalized_email.split("@")[-1]:
        errors.append("Enter a valid email address.")
    if len(password) < 8:
        errors.append("Password must contain at least 8 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if role not in {"user", "organizer"}:
        errors.append("Choose either a member or organizer account.")
    return errors


def validate_sign_in(email: str, password: str) -> list[str]:
    errors: list[str] = []
    if not normalize_email(email):
        errors.append("Email is required.")
    if not password:
        errors.append("Password is required.")
    return errors


def validate_event_payload(payload: dict[str, Any], now_value: datetime) -> list[str]:
    errors: list[str] = []
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    city = str(payload.get("city", "")).strip()
    venue = str(payload.get("venue", "")).strip()
    category = str(payload.get("category", "")).strip()
    event_datetime = payload.get("event_datetime")
    price_kzt = int(payload.get("price_kzt", 0))
    capacity = int(payload.get("capacity", 0))
    image_url = str(payload.get("image_url", "")).strip()

    if len(title) < 5:
        errors.append("Event title must contain at least 5 characters.")
    if len(description) < 40:
        errors.append("Description should be more detailed for attendees.")
    if not category:
        errors.append("Choose an event category.")
    if not city:
        errors.append("Choose a city.")
    if len(venue) < 3:
        errors.append("Venue is required.")
    if event_datetime is None or event_datetime <= now_value:
        errors.append("Event date and time must be in the future.")
    if price_kzt < 0:
        errors.append("Ticket price cannot be negative.")
    if capacity <= 0:
        errors.append("Capacity must be greater than zero.")
    if image_url and not image_url.startswith(("http://", "https://")):
        errors.append("Image URL must start with http:// or https://.")
    if slugify(title) == "event":
        errors.append("Event title must contain letters or numbers.")
    return errors
