from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from core.config import settings
from db.database import session_scope
from db.models import Booking, Event, Ticket
from db.repositories import BookingRepository, EventRepository, TicketRepository, UserRepository, get_paid_counts_by_event
from services.event_service import derive_event_runtime_status, serialize_event
from services.qr_service import parse_ticket_lookup
from utils.date_utils import now_local


def expire_pending_bookings() -> None:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)


def create_pending_booking(user_id: int, event_id: int) -> tuple[dict[str, Any] | None, list[str]]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)

        user = UserRepository(session).get_by_id(user_id)
        event = EventRepository(session).get_by_id(event_id)
        if user is None or event is None:
            return None, ["We could not load the booking context."]
        if not user.is_active:
            return None, ["Your account is inactive."]

        sold_count = get_paid_counts_by_event(session, [event.id]).get(event.id, 0)
        snapshot = serialize_event(event, sold_count, 0)
        if not snapshot["can_book"]:
            return None, ["This event is not open for booking."]

        existing_paid = BookingRepository(session).get_paid_for_user_event(user.id, event.id)
        if existing_paid is not None:
            return {
                "booking_id": existing_paid.id,
                "status": existing_paid.status,
                "ticket_id": existing_paid.ticket.id if existing_paid.ticket else None,
                "event_id": event.id,
            }, ["You already have a paid ticket for this event."]

        existing_pending = BookingRepository(session).get_pending_for_user_event(user.id, event.id)
        if existing_pending is not None and (existing_pending.expires_at is None or existing_pending.expires_at > now_local()):
            return {
                "booking_id": existing_pending.id,
                "status": existing_pending.status,
                "ticket_id": existing_pending.ticket.id if existing_pending.ticket else None,
                "event_id": event.id,
            }, []

        booking = BookingRepository(session).create(
            user_id=user.id,
            event_id=event.id,
            status="pending_payment",
            amount_kzt=event.price_kzt,
            expires_at=now_local() + timedelta(minutes=settings.payment_window_minutes),
        )
        return {
            "booking_id": booking.id,
            "status": booking.status,
            "ticket_id": None,
            "event_id": event.id,
        }, []


def get_user_ticket_rows(user_id: int) -> list[dict[str, Any]]:
    expire_pending_bookings()
    with session_scope() as session:
        tickets = TicketRepository(session).list_for_user(user_id)
        rows = []
        for ticket in tickets:
            sold_count = get_paid_counts_by_event(session, [ticket.event_id]).get(ticket.event_id, 0)
            event_snapshot = serialize_event(ticket.event, sold_count, 1 if ticket.status == "used" else 0)
            rows.append(
                {
                    "id": ticket.id,
                    "ticket_code": ticket.ticket_code,
                    "status": ticket.status,
                    "checked_in_at": ticket.checked_in_at,
                    "created_at": ticket.created_at,
                    "event": event_snapshot,
                }
            )
        return rows


def get_ticket_detail(ticket_id: int, actor: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    with session_scope() as session:
        ticket = TicketRepository(session).get_by_id(ticket_id)
        if ticket is None:
            return None, "Ticket not found."
        if actor is not None and actor["role"] != "admin" and actor["id"] not in {ticket.user_id, ticket.event.organizer_id}:
            return None, "You are not allowed to view this ticket."

        sold_count = get_paid_counts_by_event(session, [ticket.event_id]).get(ticket.event_id, 0)
        return (
            {
                "id": ticket.id,
                "ticket_code": ticket.ticket_code,
                "qr_payload": ticket.qr_payload,
                "status": ticket.status,
                "created_at": ticket.created_at,
                "checked_in_at": ticket.checked_in_at,
                "user_name": ticket.user.full_name,
                "user_email": ticket.user.email,
                "booking_id": ticket.booking_id,
                "event": serialize_event(ticket.event, sold_count, 1 if ticket.status == "used" else 0),
            },
            None,
        )


def validate_ticket_for_check_in(
    actor: dict[str, Any],
    event_id: int | None,
    ticket_code: str = "",
    qr_payload_text: str = "",
) -> dict[str, Any]:
    code = ticket_code.strip().upper() or parse_ticket_lookup(qr_payload_text or "") or ""
    if not code:
        return {"status": "not_found", "message": "Enter a ticket code or paste the QR payload text."}

    with session_scope() as session:
        ticket = TicketRepository(session).get_by_code(code)
        if ticket is None:
            return {"status": "not_found", "message": "Ticket not found."}

        if actor["role"] == "organizer" and ticket.event.organizer_id != actor["id"]:
            return {"status": "unauthorized", "message": "You can validate tickets only for your own events."}

        if event_id is not None and ticket.event_id != event_id:
            return {"status": "wrong_event", "message": "This ticket belongs to a different event."}

        if ticket.status == "cancelled":
            return {"status": "cancelled", "message": "This ticket has been cancelled.", "ticket_id": ticket.id}
        if ticket.status == "used":
            return {
                "status": "used",
                "message": "This ticket has already been checked in.",
                "ticket_id": ticket.id,
                "checked_in_at": ticket.checked_in_at,
            }

        return {
            "status": "valid",
            "message": "Valid ticket. Ready to check in.",
            "ticket_id": ticket.id,
            "ticket_code": ticket.ticket_code,
            "attendee_name": ticket.user.full_name,
            "attendee_email": ticket.user.email,
            "event_title": ticket.event.title,
        }


def check_in_ticket(actor: dict[str, Any], ticket_id: int) -> tuple[bool, str]:
    with session_scope() as session:
        ticket = TicketRepository(session).get_by_id(ticket_id)
        if ticket is None:
            return False, "Ticket not found."
        if actor["role"] == "organizer" and ticket.event.organizer_id != actor["id"]:
            return False, "You can validate tickets only for your own events."
        if ticket.status == "cancelled":
            return False, "Cancelled tickets cannot be checked in."
        if ticket.status == "used":
            return False, "This ticket has already been used."

        ticket.status = "used"
        ticket.checked_in_at = now_local()
        session.add(ticket)
        return True, f"{ticket.user.full_name} has been checked in."


def _expire_pending_bookings_in_session(session) -> None:
    current_time = now_local()
    stmt = select(Booking).where(Booking.status == "pending_payment")
    pending = session.scalars(stmt).all()
    for booking in pending:
        if booking.expires_at is not None and booking.expires_at <= current_time:
            booking.status = "expired"
            if booking.payment is not None and booking.payment.status == "pending":
                booking.payment.status = "failed"
            session.add(booking)
