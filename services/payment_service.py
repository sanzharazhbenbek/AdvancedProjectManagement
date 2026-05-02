from __future__ import annotations

import secrets
from typing import Any

from db.database import session_scope
from db.models import Ticket
from db.repositories import BookingRepository, PaymentSimulationRepository, TicketRepository, get_checked_in_counts_by_event, get_paid_counts_by_event
from services.booking_service import _expire_pending_bookings_in_session
from services.event_service import derive_event_runtime_status, serialize_event
from services.qr_service import build_payment_payload, build_ticket_payload
from utils.date_utils import now_local


def get_payment_context(booking_id: int) -> tuple[dict[str, Any] | None, str | None]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        booking = BookingRepository(session).get_by_id(booking_id)
        if booking is None:
            return None, "Booking not found."

        payment = _ensure_payment(session, booking.id)
        sold_map = get_paid_counts_by_event(session, [booking.event_id])
        checked_map = get_checked_in_counts_by_event(session, [booking.event_id])
        event_snapshot = serialize_event(booking.event, sold_map.get(booking.event_id, 0), checked_map.get(booking.event_id, 0))
        return (
            {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "amount_kzt": booking.amount_kzt,
                "created_at": booking.created_at,
                "expires_at": booking.expires_at,
                "paid_at": booking.paid_at,
                "ticket_id": booking.ticket.id if booking.ticket else None,
                "event": event_snapshot,
                "payment": {
                    "id": payment.id,
                    "provider": payment.provider,
                    "status": payment.status,
                    "payment_reference": payment.payment_reference,
                    "qr_payload": payment.qr_payload,
                    "created_at": payment.created_at,
                    "confirmed_at": payment.confirmed_at,
                },
            },
            None,
        )


def confirm_payment(booking_id: int) -> tuple[dict[str, Any] | None, list[str]]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        booking = BookingRepository(session).get_by_id(booking_id)
        if booking is None:
            return None, ["Booking not found."]

        payment = _ensure_payment(session, booking.id)
        if booking.status == "cancelled":
            payment.status = "cancelled"
            return None, ["This booking has already been cancelled."]
        if booking.status == "expired":
            payment.status = "failed"
            return None, ["The payment window has expired. Please start a new booking."]
        if booking.status == "paid" and booking.ticket is not None:
            return {"ticket_id": booking.ticket.id, "booking_id": booking.id}, []

        sold_count = get_paid_counts_by_event(session, [booking.event_id]).get(booking.event_id, 0)
        runtime_status = derive_event_runtime_status(booking.event, sold_count)
        if runtime_status in {"past", "cancelled"}:
            booking.status = "cancelled"
            payment.status = "cancelled"
            return None, ["This event is no longer available for ticketing."]
        if sold_count >= booking.event.capacity:
            booking.status = "expired"
            payment.status = "failed"
            return None, ["Tickets sold out before this payment was confirmed."]

        other_paid = BookingRepository(session).get_paid_for_user_event(booking.user_id, booking.event_id)
        if other_paid is not None and other_paid.id != booking.id:
            booking.status = "cancelled"
            payment.status = "cancelled"
            return None, ["A paid ticket already exists for this attendee."]

        ticket = booking.ticket
        if ticket is None:
            ticket = TicketRepository(session).create(
                booking_id=booking.id,
                user_id=booking.user_id,
                event_id=booking.event_id,
                ticket_code=f"ES-{secrets.token_hex(4).upper()}",
                qr_payload="pending",
                status="valid",
            )
            session.flush()
            ticket.qr_payload = build_ticket_payload(ticket.id, ticket.ticket_code)

        booking.status = "paid"
        booking.paid_at = now_local()
        payment.status = "confirmed"
        payment.confirmed_at = booking.paid_at
        session.add_all([booking, payment, ticket])
        return {"ticket_id": ticket.id, "booking_id": booking.id}, []


def cancel_payment(booking_id: int) -> tuple[bool, str]:
    with session_scope() as session:
        booking = BookingRepository(session).get_by_id(booking_id)
        if booking is None:
            return False, "Booking not found."

        payment = _ensure_payment(session, booking.id)
        if booking.status == "paid":
            return False, "Paid bookings cannot be cancelled from the sandbox page."
        if booking.status in {"cancelled", "expired"}:
            return False, "This booking is already closed."

        booking.status = "cancelled"
        booking.cancelled_at = now_local()
        payment.status = "cancelled"
        session.add_all([booking, payment])
        return True, "Booking cancelled."


def _ensure_payment(session, booking_id: int):
    payment_repo = PaymentSimulationRepository(session)
    payment = payment_repo.get_by_booking_id(booking_id)
    if payment is not None:
        payment.qr_payload = build_payment_payload(booking_id, payment.payment_reference)
        session.add(payment)
        return payment

    payment = payment_repo.create(
        booking_id=booking_id,
        provider="kaspi_sandbox",
        status="pending",
        payment_reference=f"KSP-{secrets.token_hex(4).upper()}",
        qr_payload=build_payment_payload(booking_id),
    )
    payment.qr_payload = build_payment_payload(booking_id, payment.payment_reference)
    session.add(payment)
    return payment
