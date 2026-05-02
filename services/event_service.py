from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select

from db.database import session_scope
from db.models import Booking, Event, Ticket
from db.repositories import (
    BookingRepository,
    EventRepository,
    TicketRepository,
    UserRepository,
    get_checked_in_counts_by_event,
    get_paid_counts_by_event,
    get_revenue_by_event,
)
from utils.date_utils import now_local
from utils.formatters import slugify
from utils.validators import validate_event_payload


def derive_event_runtime_status(event: Event, sold_count: int, reference_time=None) -> str:
    current_time = reference_time or now_local()
    if event.status == "cancelled":
        return "cancelled"
    if event.event_datetime < current_time:
        return "past"
    if sold_count >= event.capacity:
        return "sold_out"
    return "upcoming"


def can_book_event(snapshot: dict[str, Any]) -> bool:
    return snapshot["runtime_status"] == "upcoming" and snapshot["remaining_count"] > 0


def serialize_event(event: Event, sold_count: int, checked_in_count: int, viewer_booking: Booking | None = None) -> dict[str, Any]:
    runtime_status = derive_event_runtime_status(event, sold_count)
    remaining = max(event.capacity - sold_count, 0)
    return {
        "id": event.id,
        "slug": event.slug,
        "title": event.title,
        "description": event.description,
        "category": event.category,
        "city": event.city,
        "venue": event.venue,
        "event_datetime": event.event_datetime,
        "price_kzt": event.price_kzt,
        "capacity": event.capacity,
        "image_url": event.image_url,
        "organizer_id": event.organizer_id,
        "organizer_name": event.organizer.full_name if event.organizer else "Unknown organizer",
        "status": event.status,
        "runtime_status": runtime_status,
        "sold_count": sold_count,
        "checked_in_count": checked_in_count,
        "remaining_count": remaining,
        "fill_rate": (sold_count / event.capacity) if event.capacity else 0,
        "can_book": runtime_status == "upcoming" and remaining > 0,
        "viewer_has_paid_ticket": bool(viewer_booking and viewer_booking.status == "paid"),
        "viewer_ticket_id": viewer_booking.ticket.id if viewer_booking and viewer_booking.ticket else None,
    }


def list_discover_events(filters: dict[str, Any] | None = None, viewer_id: int | None = None) -> dict[str, Any]:
    filters = filters or {}
    search = str(filters.get("search", "")).strip().lower()
    category = str(filters.get("category", "All"))
    city = str(filters.get("city", "All"))
    date_scope = str(filters.get("date_scope", "upcoming"))
    sort_by = str(filters.get("sort_by", "date"))

    with session_scope() as session:
        events = EventRepository(session).list_all()
        event_ids = [event.id for event in events]
        sold_map = get_paid_counts_by_event(session, event_ids)
        checked_map = get_checked_in_counts_by_event(session, event_ids)
        viewer_bookings: dict[int, Booking] = {}
        if viewer_id is not None:
            bookings = BookingRepository(session).list_for_user(viewer_id)
            viewer_bookings = {booking.event_id: booking for booking in bookings if booking.status == "paid"}

        snapshots = [
            serialize_event(
                event,
                sold_map.get(event.id, 0),
                checked_map.get(event.id, 0),
                viewer_bookings.get(event.id),
            )
            for event in events
        ]

        categories = sorted({item["category"] for item in snapshots})
        cities = sorted({item["city"] for item in snapshots})

        def matches(item: dict[str, Any]) -> bool:
            haystack = " ".join([item["title"], item["category"], item["city"], item["venue"]]).lower()
            if search and search not in haystack:
                return False
            if category != "All" and item["category"] != category:
                return False
            if city != "All" and item["city"] != city:
                return False
            if date_scope == "upcoming" and item["runtime_status"] not in {"upcoming", "sold_out"}:
                return False
            if date_scope == "past" and item["runtime_status"] != "past":
                return False
            return True

        filtered = [item for item in snapshots if matches(item)]

        def sort_key(item: dict[str, Any]):
            if sort_by == "price":
                return (item["price_kzt"], item["event_datetime"])
            if sort_by == "popularity":
                return (-item["sold_count"], item["event_datetime"])
            if sort_by == "remaining":
                return (item["remaining_count"], item["event_datetime"])
            return (item["event_datetime"], item["title"])

        filtered.sort(key=sort_key)

        featured = None
        upcoming_events = [item for item in snapshots if item["runtime_status"] in {"upcoming", "sold_out"}]
        if upcoming_events:
            featured = sorted(upcoming_events, key=lambda item: (-item["sold_count"], item["event_datetime"]))[0]
        elif snapshots:
            featured = snapshots[0]

        return {
            "events": filtered,
            "featured": featured,
            "categories": categories,
            "cities": cities,
            "stats": {
                "total_events": len(snapshots),
                "upcoming_events": len([item for item in snapshots if item["runtime_status"] == "upcoming"]),
                "sold_out_events": len([item for item in snapshots if item["runtime_status"] == "sold_out"]),
                "cities": len(cities),
            },
        }


def get_event_detail(event_id: int, viewer_id: int | None = None) -> dict[str, Any] | None:
    with session_scope() as session:
        event = EventRepository(session).get_by_id(event_id)
        if event is None:
            return None
        sold_map = get_paid_counts_by_event(session, [event.id])
        checked_map = get_checked_in_counts_by_event(session, [event.id])
        viewer_booking = None
        if viewer_id is not None:
            viewer_booking = BookingRepository(session).get_paid_for_user_event(viewer_id, event.id)
        return serialize_event(event, sold_map.get(event.id, 0), checked_map.get(event.id, 0), viewer_booking)


def create_event(actor: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    now_value = now_local()
    errors = validate_event_payload(payload, now_value)
    if actor["role"] not in {"organizer", "admin"}:
        errors.append("You do not have permission to create events.")
    if errors:
        return None, errors

    with session_scope() as session:
        user = UserRepository(session).get_by_id(actor["id"])
        if user is None:
            return None, ["Your account could not be loaded."]

        base_slug = slugify(payload["title"])
        slug = _unique_slug(session, base_slug)
        event = EventRepository(session).create(
            title=payload["title"].strip(),
            slug=slug,
            description=payload["description"].strip(),
            category=payload["category"].strip(),
            city=payload["city"].strip(),
            venue=payload["venue"].strip(),
            event_datetime=payload["event_datetime"],
            price_kzt=int(payload["price_kzt"]),
            capacity=int(payload["capacity"]),
            image_url=payload.get("image_url", "").strip() or None,
            organizer_id=user.id,
            status="scheduled",
        )
        session.refresh(event)
        sold_map = get_paid_counts_by_event(session, [event.id])
        checked_map = get_checked_in_counts_by_event(session, [event.id])
        return serialize_event(event, sold_map.get(event.id, 0), checked_map.get(event.id, 0)), []


def update_event(actor: dict[str, Any], event_id: int, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    now_value = now_local()
    errors = validate_event_payload(payload, now_value)
    with session_scope() as session:
        event = EventRepository(session).get_by_id(event_id)
        if event is None:
            return None, ["Event not found."]
        if not _can_manage_event(actor, event):
            return None, ["You cannot edit this event."]

        sold_count = get_paid_counts_by_event(session, [event.id]).get(event.id, 0)
        if payload["capacity"] < sold_count:
            errors.append("Capacity cannot be lower than tickets already sold.")
        if errors:
            return None, errors

        event.title = payload["title"].strip()
        event.slug = _unique_slug(session, slugify(payload["title"]), exclude_event_id=event.id)
        event.description = payload["description"].strip()
        event.category = payload["category"].strip()
        event.city = payload["city"].strip()
        event.venue = payload["venue"].strip()
        event.event_datetime = payload["event_datetime"]
        event.price_kzt = int(payload["price_kzt"])
        event.capacity = int(payload["capacity"])
        event.image_url = payload.get("image_url", "").strip() or None
        session.add(event)
        session.flush()
        checked_map = get_checked_in_counts_by_event(session, [event.id])
        return serialize_event(event, sold_count, checked_map.get(event.id, 0)), []


def cancel_event(actor: dict[str, Any], event_id: int) -> tuple[bool, str]:
    with session_scope() as session:
        event = EventRepository(session).get_by_id(event_id)
        if event is None:
            return False, "Event not found."
        if not _can_manage_event(actor, event):
            return False, "You cannot cancel this event."

        event.status = "cancelled"
        for booking in event.bookings:
            if booking.status == "pending_payment":
                booking.status = "cancelled"
                booking.cancelled_at = now_local()
                if booking.payment is not None:
                    booking.payment.status = "cancelled"
        for ticket in event.tickets:
            if ticket.status == "valid":
                ticket.status = "cancelled"
        session.add(event)
        return True, f"{event.title} has been cancelled."


def list_organizer_events(actor: dict[str, Any]) -> list[dict[str, Any]]:
    with session_scope() as session:
        events = EventRepository(session).list_by_organizer(actor["id"])
        event_ids = [event.id for event in events]
        sold_map = get_paid_counts_by_event(session, event_ids)
        checked_map = get_checked_in_counts_by_event(session, event_ids)
        return [serialize_event(event, sold_map.get(event.id, 0), checked_map.get(event.id, 0)) for event in events]


def list_all_events_for_admin() -> list[dict[str, Any]]:
    with session_scope() as session:
        events = EventRepository(session).list_all()
        event_ids = [event.id for event in events]
        sold_map = get_paid_counts_by_event(session, event_ids)
        checked_map = get_checked_in_counts_by_event(session, event_ids)
        revenue_map = get_revenue_by_event(session, event_ids)
        rows = []
        for event in events:
            snapshot = serialize_event(event, sold_map.get(event.id, 0), checked_map.get(event.id, 0))
            snapshot["revenue_kzt"] = revenue_map.get(event.id, 0)
            rows.append(snapshot)
        return rows


def list_event_attendees(actor: dict[str, Any], event_id: int) -> tuple[list[dict[str, Any]], str | None]:
    with session_scope() as session:
        event = EventRepository(session).get_by_id(event_id)
        if event is None:
            return [], "Event not found."
        if not _can_manage_event(actor, event):
            return [], "You are not allowed to view attendees for this event."

        tickets = TicketRepository(session).list_for_event(event_id)
        rows = [
            {
                "ticket_id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "attendee_name": ticket.user.full_name,
                "attendee_email": ticket.user.email,
                "status": ticket.status,
                "checked_in_at": ticket.checked_in_at,
                "booking_id": ticket.booking_id,
            }
            for ticket in tickets
        ]
        return rows, None


def list_recent_bookings() -> list[dict[str, Any]]:
    with session_scope() as session:
        bookings = BookingRepository(session).list_recent(limit=12)
        return [_serialize_booking_row(item) for item in bookings]


def list_all_user_rows() -> list[dict[str, Any]]:
    with session_scope() as session:
        users = UserRepository(session).list_all()
        return [
            {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
            for user in users
        ]


def deactivate_user(actor: dict[str, Any], user_id: int) -> tuple[bool, str]:
    if actor["role"] != "admin":
        return False, "Only admins can deactivate users."
    with session_scope() as session:
        user = UserRepository(session).get_by_id(user_id)
        if user is None:
            return False, "User not found."
        if user.role == "admin" and user.id == actor["id"]:
            return False, "You cannot deactivate your own admin account."
        user.is_active = False
        session.add(user)
        return True, f"{user.full_name} has been deactivated."


def _unique_slug(session, base_slug: str, exclude_event_id: int | None = None) -> str:
    slug = base_slug or f"event-{secrets.token_hex(3)}"
    candidate = slug
    counter = 2
    while True:
        stmt = select(Event).where(Event.slug == candidate)
        if exclude_event_id is not None:
            stmt = stmt.where(Event.id != exclude_event_id)
        existing = session.scalar(stmt)
        if existing is None:
            return candidate
        candidate = f"{slug}-{counter}"
        counter += 1


def _can_manage_event(actor: dict[str, Any], event: Event) -> bool:
    return actor["role"] == "admin" or event.organizer_id == actor["id"]


def _serialize_booking_row(booking: Booking) -> dict[str, Any]:
    return {
        "id": booking.id,
        "status": booking.status,
        "amount_kzt": booking.amount_kzt,
        "created_at": booking.created_at,
        "paid_at": booking.paid_at,
        "event_title": booking.event.title if booking.event else "Unknown event",
        "user_name": booking.user.full_name if booking.user else "Unknown attendee",
        "user_email": booking.user.email if booking.user else "Unknown attendee",
        "payment_reference": booking.payment.payment_reference if booking.payment else None,
        "ticket_id": booking.ticket.id if booking.ticket else None,
    }
