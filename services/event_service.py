from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select

from db.database import session_scope
from db.models import Booking, Event, Seat
from db.repositories import (
    BookingRepository,
    EmailLogRepository,
    EventRepository,
    PaymentSimulationRepository,
    SeatRepository,
    TicketRepository,
    UserRepository,
    get_available_counts_by_event,
    get_checked_in_counts_by_event,
    get_paid_counts_by_event,
    get_reserved_counts_by_event,
    get_revenue_by_event,
)
from services.seat_service import build_seat_inventory_payload, price_by_category, sync_event_seats
from utils.date_utils import now_local
from utils.formatters import slugify
from utils.validators import validate_event_payload


def derive_event_runtime_status(event: Event, sold_count: int, available_count: int | None = None, reference_time=None) -> str:
    current_time = reference_time or now_local()
    if event.status == "cancelled":
        return "cancelled"
    if event.event_datetime < current_time:
        return "past"
    if available_count is not None and available_count <= 0:
        return "sold_out"
    if sold_count >= event.capacity:
        return "sold_out"
    return "upcoming"


def can_book_event(snapshot: dict[str, Any]) -> bool:
    return snapshot["runtime_status"] == "upcoming" and snapshot["remaining_count"] > 0


def serialize_event(
    event: Event,
    sold_count: int,
    checked_in_count: int,
    viewer_booking: Booking | dict[str, Any] | None = None,
    *,
    available_count: int | None = None,
    reserved_count: int = 0,
) -> dict[str, Any]:
    remaining = available_count if available_count is not None else max(event.capacity - sold_count, 0)
    runtime_status = derive_event_runtime_status(event, sold_count, remaining)
    viewer_context = _normalize_viewer_context(viewer_booking)
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
        "price_from_kzt": event.price_kzt,
        "capacity": event.capacity,
        "image_url": event.image_url,
        "organizer_id": event.organizer_id,
        "organizer_name": event.organizer.full_name if event.organizer else "Unknown organizer",
        "status": event.status,
        "runtime_status": runtime_status,
        "sold_count": sold_count,
        "checked_in_count": checked_in_count,
        "remaining_count": remaining,
        "reserved_count": reserved_count,
        "fill_rate": (sold_count / event.capacity) if event.capacity else 0,
        "can_book": runtime_status == "upcoming" and remaining > 0,
        "viewer_has_paid_ticket": viewer_context["viewer_has_paid_ticket"],
        "viewer_paid_ticket_count": viewer_context["viewer_paid_ticket_count"],
        "viewer_ticket_id": viewer_context["viewer_ticket_id"],
        "viewer_pending_booking_id": viewer_context["viewer_pending_booking_id"],
        "viewer_pending_ticket_count": viewer_context["viewer_pending_ticket_count"],
        "viewer_pending_total_amount_kzt": viewer_context["viewer_pending_total_amount_kzt"],
        "viewer_pending_seat": viewer_context["viewer_pending_seat"],
        "viewer_pending_seats": viewer_context["viewer_pending_seats"],
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
        available_map = get_available_counts_by_event(session, event_ids)
        reserved_map = get_reserved_counts_by_event(session, event_ids)
        viewer_bookings: dict[int, dict[str, Any]] = {}
        if viewer_id is not None:
            bookings = BookingRepository(session).list_for_user(viewer_id)
            bookings_by_event: dict[int, list[Booking]] = {}
            for booking in bookings:
                if booking.status not in {"paid", "pending_payment"}:
                    continue
                bookings_by_event.setdefault(booking.event_id, []).append(booking)
            viewer_bookings = {
                event_id: _build_viewer_booking_context(bookings_for_event)
                for event_id, bookings_for_event in bookings_by_event.items()
            }

        snapshots = [
            serialize_event(
                event,
                sold_map.get(event.id, 0),
                checked_map.get(event.id, 0),
                viewer_bookings.get(event.id),
                available_count=available_map.get(event.id, 0),
                reserved_count=reserved_map.get(event.id, 0),
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
                return (item["price_from_kzt"], item["event_datetime"])
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
        available_map = get_available_counts_by_event(session, [event.id])
        reserved_map = get_reserved_counts_by_event(session, [event.id])
        viewer_booking = None
        if viewer_id is not None:
            bookings = BookingRepository(session).list_for_user_event(viewer_id, event.id)
            viewer_booking = _build_viewer_booking_context(
                [booking for booking in bookings if booking.status in {"paid", "pending_payment"}]
            )
        return serialize_event(
            event,
            sold_map.get(event.id, 0),
            checked_map.get(event.id, 0),
            viewer_booking,
            available_count=available_map.get(event.id, 0),
            reserved_count=reserved_map.get(event.id, 0),
        )


def get_event_seat_inventory(event_id: int, actor: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    with session_scope() as session:
        event = EventRepository(session).get_by_id(event_id)
        if event is None:
            return None, "Event not found."
        if actor and actor["role"] == "organizer" and event.organizer_id != actor["id"]:
            return None, "You can only view seats for your own events."

        seats = SeatRepository(session).list_for_event(event_id)
        payload = build_seat_inventory_payload(seats)
        payload["event_id"] = event.id
        payload["event_title"] = event.title
        return payload, None


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
        sync_event_seats(session, event, mode="dynamic", target_capacity=int(payload["capacity"]), force_regenerate=True)
        session.refresh(event)
        sold_map = get_paid_counts_by_event(session, [event.id])
        checked_map = get_checked_in_counts_by_event(session, [event.id])
        available_map = get_available_counts_by_event(session, [event.id])
        return (
            serialize_event(
                event,
                sold_map.get(event.id, 0),
                checked_map.get(event.id, 0),
                available_count=available_map.get(event.id, 0),
            ),
            [],
        )


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
        seats = SeatRepository(session).list_for_event(event.id)
        occupied_seats = [seat for seat in seats if seat.status != "available"]
        target_capacity = int(payload["capacity"])
        if target_capacity < sold_count:
            errors.append("Capacity cannot be lower than tickets already sold.")
        if occupied_seats and target_capacity != len(seats):
            errors.append("Capacity cannot be changed while seats are sold or reserved.")
        if errors:
            return None, errors

        event.title = payload["title"].strip()
        event.slug = _unique_slug(session, slugify(payload["title"]), exclude_event_id=event.id)
        event.description = payload["description"].strip()
        event.category = payload["category"].strip()
        event.city = payload["city"].strip()
        event.venue = payload["venue"].strip()
        event.event_datetime = payload["event_datetime"]
        event.image_url = payload.get("image_url", "").strip() or None
        old_base_price = event.price_kzt
        event.price_kzt = int(payload["price_kzt"])

        if not occupied_seats and (target_capacity != len(seats) or old_base_price != event.price_kzt):
            sync_event_seats(session, event, mode="dynamic", target_capacity=target_capacity, force_regenerate=True)
        elif old_base_price != event.price_kzt and seats:
            category_prices = price_by_category(event.price_kzt)
            for seat in seats:
                if seat.status == "available":
                    seat.price_kzt = category_prices[seat.category]
                    session.add(seat)
            event.price_kzt = min(category_prices.values())

        session.add(event)
        session.flush()
        checked_map = get_checked_in_counts_by_event(session, [event.id])
        available_map = get_available_counts_by_event(session, [event.id])
        reserved_map = get_reserved_counts_by_event(session, [event.id])
        return (
            serialize_event(
                event,
                sold_count,
                checked_map.get(event.id, 0),
                available_count=available_map.get(event.id, 0),
                reserved_count=reserved_map.get(event.id, 0),
            ),
            [],
        )


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
                if booking.seat is not None:
                    booking.seat.status = "available"
                    booking.seat.booking_id = None
                    session.add(booking.seat)
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
        available_map = get_available_counts_by_event(session, event_ids)
        reserved_map = get_reserved_counts_by_event(session, event_ids)
        return [
            serialize_event(
                event,
                sold_map.get(event.id, 0),
                checked_map.get(event.id, 0),
                available_count=available_map.get(event.id, 0),
                reserved_count=reserved_map.get(event.id, 0),
            )
            for event in events
        ]


def list_all_events_for_admin() -> list[dict[str, Any]]:
    with session_scope() as session:
        events = EventRepository(session).list_all()
        event_ids = [event.id for event in events]
        sold_map = get_paid_counts_by_event(session, event_ids)
        checked_map = get_checked_in_counts_by_event(session, event_ids)
        available_map = get_available_counts_by_event(session, event_ids)
        reserved_map = get_reserved_counts_by_event(session, event_ids)
        revenue_map = get_revenue_by_event(session, event_ids)
        rows = []
        for event in events:
            snapshot = serialize_event(
                event,
                sold_map.get(event.id, 0),
                checked_map.get(event.id, 0),
                available_count=available_map.get(event.id, 0),
                reserved_count=reserved_map.get(event.id, 0),
            )
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
        booking_primary_map = _build_group_primary_map([ticket.booking for ticket in tickets if ticket.booking is not None])
        rows = []
        for ticket in tickets:
            payment_booking = _resolve_group_payment_booking(ticket.booking, booking_primary_map) if ticket.booking else None
            rows.append(
                {
                    "ticket_id": ticket.id,
                    "ticket_code": ticket.ticket_code,
                    "attendee_name": ticket.user.full_name,
                    "attendee_email": ticket.user.email,
                    "status": ticket.status,
                    "checked_in_at": ticket.checked_in_at,
                    "booking_id": ticket.booking_id,
                    "payment_status": payment_booking.payment.status if payment_booking and payment_booking.payment else None,
                    "seat_category": ticket.category,
                    "row_label": ticket.row_label,
                    "seat_number": ticket.seat_number,
                    "price_kzt": ticket.price_kzt,
                }
            )
        return rows, None


def list_recent_bookings() -> list[dict[str, Any]]:
    with session_scope() as session:
        bookings = BookingRepository(session).list_recent(limit=12)
        booking_primary_map = _build_group_primary_map(bookings)
        return [_serialize_booking_row(item, booking_primary_map) for item in bookings]


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


def list_admin_operational_rows() -> dict[str, list[dict[str, Any]]]:
    with session_scope() as session:
        bookings = BookingRepository(session).list_all()
        payments = PaymentSimulationRepository(session).list_all()
        tickets = TicketRepository(session).list_all()
        email_logs = EmailLogRepository(session).list_all()
        bookings_map = {booking.id: booking for booking in bookings}
        booking_primary_map = _build_group_primary_map(bookings)
        booking_group_totals = _build_group_total_map(bookings)

        return {
            "bookings": [_serialize_booking_row(booking, booking_primary_map) for booking in bookings],
            "payments": [
                {
                    "payment_id": payment.id,
                    "booking_id": payment.booking_id,
                    "provider": payment.provider,
                    "status": payment.status,
                    "payment_reference": payment.payment_reference,
                    "created_at": payment.created_at,
                    "confirmed_at": payment.confirmed_at,
                    "event_title": payment.booking.event.title if payment.booking and payment.booking.event else None,
                    "user_email": payment.booking.customer_email if payment.booking else None,
                    "amount_kzt": booking_group_totals.get(_booking_group_key(payment.booking), payment.booking.amount_kzt)
                    if payment.booking
                    else None,
                }
                for payment in payments
            ],
            "tickets": [
                {
                    "ticket_id": ticket.id,
                    "ticket_code": ticket.ticket_code,
                    "event_title": ticket.event.title if ticket.event else None,
                    "user_email": ticket.user.email if ticket.user else None,
                    "status": ticket.status,
                    "category": ticket.category,
                    "row_label": ticket.row_label,
                    "seat_number": ticket.seat_number,
                    "price_kzt": ticket.price_kzt,
                    "created_at": ticket.created_at,
                    "checked_in_at": ticket.checked_in_at,
                }
                for ticket in tickets
            ],
            "email_logs": [
                {
                    "email_log_id": email_log.id,
                    "recipient_email": email_log.recipient_email,
                    "subject": email_log.subject,
                    "status": email_log.status,
                    "attachment_path": email_log.attachment_path,
                    "created_at": email_log.created_at,
                    "booking_id": email_log.booking_id,
                    "ticket_id": email_log.ticket_id,
                    "event_title": bookings_map.get(email_log.booking_id).event.title
                    if email_log.booking_id and email_log.booking_id in bookings_map and bookings_map[email_log.booking_id].event
                    else None,
                    "user_email": bookings_map.get(email_log.booking_id).customer_email
                    if email_log.booking_id and email_log.booking_id in bookings_map
                    else email_log.recipient_email,
                }
                for email_log in email_logs
            ],
        }


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


def _serialize_booking_row(booking: Booking, booking_primary_map: dict[str, Booking] | None = None) -> dict[str, Any]:
    payment_booking = _resolve_group_payment_booking(booking, booking_primary_map)
    return {
        "id": booking.id,
        "status": booking.status,
        "amount_kzt": booking.amount_kzt,
        "created_at": booking.created_at,
        "paid_at": booking.paid_at,
        "event_id": booking.event_id,
        "event_title": booking.event.title if booking.event else "Unknown event",
        "user_name": booking.user.full_name if booking.user else "Unknown attendee",
        "user_email": booking.customer_email or (booking.user.email if booking.user else None),
        "payment_reference": payment_booking.payment.payment_reference if payment_booking.payment else None,
        "payment_status": payment_booking.payment.status if payment_booking.payment else None,
        "ticket_id": booking.ticket.id if booking.ticket else None,
        "seat_category": booking.seat.category if booking.seat else None,
        "row_label": booking.seat.row_label if booking.seat else None,
        "seat_number": booking.seat.seat_number if booking.seat else None,
        "payment_deadline": booking.payment_deadline or booking.expires_at,
    }


def _normalize_viewer_context(viewer_booking: Booking | dict[str, Any] | None) -> dict[str, Any]:
    if viewer_booking is None:
        return {
            "viewer_has_paid_ticket": False,
            "viewer_paid_ticket_count": 0,
            "viewer_ticket_id": None,
            "viewer_pending_booking_id": None,
            "viewer_pending_ticket_count": 0,
            "viewer_pending_total_amount_kzt": 0,
            "viewer_pending_seat": None,
            "viewer_pending_seats": [],
        }
    if isinstance(viewer_booking, dict):
        base_context = _normalize_viewer_context(None)
        base_context.update(viewer_booking)
        return base_context
    pending_seat = (
        {
            "category": viewer_booking.seat.category,
            "row_label": viewer_booking.seat.row_label,
            "seat_number": viewer_booking.seat.seat_number,
            "price_kzt": viewer_booking.seat.price_kzt,
        }
        if viewer_booking.seat
        else None
    )
    return {
        "viewer_has_paid_ticket": viewer_booking.status == "paid",
        "viewer_paid_ticket_count": 1 if viewer_booking.status == "paid" else 0,
        "viewer_ticket_id": viewer_booking.ticket.id if viewer_booking.ticket else None,
        "viewer_pending_booking_id": viewer_booking.id if viewer_booking.status == "pending_payment" else None,
        "viewer_pending_ticket_count": 1 if viewer_booking.status == "pending_payment" else 0,
        "viewer_pending_total_amount_kzt": viewer_booking.amount_kzt if viewer_booking.status == "pending_payment" else 0,
        "viewer_pending_seat": pending_seat,
        "viewer_pending_seats": [pending_seat] if pending_seat and viewer_booking.status == "pending_payment" else [],
    }


def _build_viewer_booking_context(bookings: list[Booking]) -> dict[str, Any]:
    if not bookings:
        return _normalize_viewer_context(None)

    paid_bookings = [booking for booking in bookings if booking.status == "paid" and booking.ticket is not None]
    pending_bookings = [booking for booking in bookings if booking.status == "pending_payment"]
    latest_paid = paid_bookings[0] if paid_bookings else None
    latest_pending_group = _select_latest_pending_group(pending_bookings)
    pending_seats = [
        {
            "category": booking.seat.category,
            "row_label": booking.seat.row_label,
            "seat_number": booking.seat.seat_number,
            "price_kzt": booking.seat.price_kzt,
        }
        for booking in latest_pending_group
        if booking.seat is not None
    ]
    return {
        "viewer_has_paid_ticket": bool(paid_bookings),
        "viewer_paid_ticket_count": len(paid_bookings),
        "viewer_ticket_id": latest_paid.ticket.id if latest_paid and latest_paid.ticket else None,
        "viewer_pending_booking_id": latest_pending_group[0].id if latest_pending_group else None,
        "viewer_pending_ticket_count": len(latest_pending_group),
        "viewer_pending_total_amount_kzt": sum(booking.amount_kzt for booking in latest_pending_group),
        "viewer_pending_seat": pending_seats[0] if pending_seats else None,
        "viewer_pending_seats": pending_seats,
    }


def _select_latest_pending_group(bookings: list[Booking]) -> list[Booking]:
    if not bookings:
        return []
    groups: dict[str, list[Booking]] = {}
    for booking in bookings:
        groups.setdefault(_booking_group_key(booking), []).append(booking)
    latest_group = max(
        groups.values(),
        key=lambda items: max((item.created_at, item.id) for item in items),
    )
    return sorted(latest_group, key=lambda item: (item.created_at, item.id))


def _booking_group_key(booking: Booking) -> str:
    return booking.booking_group_token or f"booking-{booking.id}"


def _build_group_primary_map(bookings: list[Booking]) -> dict[str, Booking]:
    primary_map: dict[str, Booking] = {}
    for booking in sorted(bookings, key=lambda item: (item.created_at, item.id)):
        group_key = _booking_group_key(booking)
        current = primary_map.get(group_key)
        if current is None or (booking.payment_confirmation_token or booking.payment is not None):
            primary_map[group_key] = booking
    return primary_map


def _build_group_total_map(bookings: list[Booking]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for booking in bookings:
        group_key = _booking_group_key(booking)
        totals[group_key] = totals.get(group_key, 0) + booking.amount_kzt
    return totals


def _resolve_group_payment_booking(
    booking: Booking,
    booking_primary_map: dict[str, Booking] | None = None,
) -> Booking:
    if booking.payment is not None or booking.booking_group_token is None:
        return booking
    if booking_primary_map is None:
        return booking
    return booking_primary_map.get(_booking_group_key(booking), booking)
