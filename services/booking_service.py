from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from core.config import settings
from db.database import session_scope
from db.models import Booking
from db.repositories import BookingRepository, EventRepository, EmailLogRepository, SeatRepository, TicketRepository, UserRepository, get_available_counts_by_event, get_paid_counts_by_event
from services.event_service import derive_event_runtime_status, serialize_event
from services.qr_service import parse_ticket_lookup
from services.seat_service import release_seat, reserve_seat_for_booking
from utils.date_utils import now_local
from utils.formatters import seat_label


def expire_pending_bookings() -> None:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)


def create_pending_booking(user_id: int, event_id: int, seat_id: int) -> tuple[dict[str, Any] | None, list[str]]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)

        user = UserRepository(session).get_by_id(user_id)
        event = EventRepository(session).get_by_id(event_id)
        seat = SeatRepository(session).get_by_id(seat_id)
        if user is None or event is None or seat is None:
            return None, ["We could not load the booking context."]
        if seat.event_id != event.id:
            return None, ["That seat does not belong to this event."]
        if not user.is_active:
            return None, ["Your account is inactive."]

        sold_count = get_paid_counts_by_event(session, [event.id]).get(event.id, 0)
        available_count = get_available_counts_by_event(session, [event.id]).get(event.id, 0)
        snapshot = serialize_event(event, sold_count, 0, available_count=available_count)
        if not snapshot["can_book"]:
            return None, ["This event is not open for booking."]

        existing_paid = BookingRepository(session).get_paid_for_user_event(user.id, event.id)
        if existing_paid is not None:
            return {
                "booking_id": existing_paid.id,
                "status": existing_paid.status,
                "ticket_id": existing_paid.ticket.id if existing_paid.ticket else None,
                "event_id": event.id,
                "seat_id": existing_paid.seat_id,
            }, ["You already have a paid ticket for this event."]

        existing_pending = BookingRepository(session).get_pending_for_user_event(user.id, event.id)
        if existing_pending is not None and (existing_pending.payment_deadline or existing_pending.expires_at) and (existing_pending.payment_deadline or existing_pending.expires_at) > now_local():
            if existing_pending.seat_id == seat.id:
                return {
                    "booking_id": existing_pending.id,
                    "status": existing_pending.status,
                    "ticket_id": existing_pending.ticket.id if existing_pending.ticket else None,
                    "event_id": event.id,
                    "seat_id": seat.id,
                }, []

            existing_pending.status = "cancelled"
            existing_pending.cancelled_at = now_local()
            if existing_pending.payment is not None:
                existing_pending.payment.status = "cancelled"
            release_seat(session, existing_pending.seat_id)
            session.add(existing_pending)

        if seat.status != "available":
            return None, ["This seat is no longer available."]

        deadline = now_local() + timedelta(minutes=settings.payment_window_minutes)
        booking = BookingRepository(session).create(
            user_id=user.id,
            event_id=event.id,
            seat_id=seat.id,
            status="pending_payment",
            amount_kzt=seat.price_kzt,
            customer_email=user.email,
            expires_at=deadline,
            payment_deadline=deadline,
            payment_confirmation_token=secrets.token_urlsafe(24),
        )
        if not reserve_seat_for_booking(session, seat.id, booking.id):
            session.delete(booking)
            session.flush()
            return None, ["Another attendee just reserved this seat. Please choose a different one."]

        return {
            "booking_id": booking.id,
            "status": booking.status,
            "ticket_id": None,
            "event_id": event.id,
            "seat_id": seat.id,
            "seat_summary": {
                "category": seat.category,
                "row_label": seat.row_label,
                "seat_number": seat.seat_number,
                "price_kzt": seat.price_kzt,
            },
        }, []


def get_user_ticket_rows(user_id: int) -> list[dict[str, Any]]:
    expire_pending_bookings()
    with session_scope() as session:
        tickets = TicketRepository(session).list_for_user(user_id)
        rows = []
        for ticket in tickets:
            sold_count = get_paid_counts_by_event(session, [ticket.event_id]).get(ticket.event_id, 0)
            available_count = get_available_counts_by_event(session, [ticket.event_id]).get(ticket.event_id, 0)
            event_snapshot = serialize_event(ticket.event, sold_count, 1 if ticket.status == "used" else 0, available_count=available_count)
            rows.append(
                {
                    "id": ticket.id,
                    "ticket_code": ticket.ticket_code,
                    "status": ticket.status,
                    "checked_in_at": ticket.checked_in_at,
                    "created_at": ticket.created_at,
                    "seat_label": seat_label(ticket.category, ticket.row_label, ticket.seat_number),
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
        available_count = get_available_counts_by_event(session, [ticket.event_id]).get(ticket.event_id, 0)
        email_logs = EmailLogRepository(session).list_for_ticket(ticket.id)
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
                "seat": {
                    "category": ticket.category,
                    "row_label": ticket.row_label,
                    "seat_number": ticket.seat_number,
                    "price_kzt": ticket.price_kzt,
                },
                "ticket_file_path": ticket.ticket_file_path,
                "email_logs": [
                    {
                        "recipient_email": email_log.recipient_email,
                        "subject": email_log.subject,
                        "status": email_log.status,
                        "attachment_path": email_log.attachment_path,
                        "created_at": email_log.created_at,
                    }
                    for email_log in email_logs
                ],
                "event": serialize_event(ticket.event, sold_count, 1 if ticket.status == "used" else 0, available_count=available_count),
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
            "seat_label": seat_label(ticket.category, ticket.row_label, ticket.seat_number),
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
        deadline = booking.payment_deadline or booking.expires_at
        if deadline is not None and deadline <= current_time:
            booking.status = "expired"
            if booking.payment is not None and booking.payment.status == "pending":
                booking.payment.status = "failed"
            release_seat(session, booking.seat_id)
            session.add(booking)
