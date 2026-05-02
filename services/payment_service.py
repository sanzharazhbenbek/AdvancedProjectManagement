from __future__ import annotations

import secrets
from typing import Any

from db.database import session_scope
from db.repositories import BookingRepository, PaymentSimulationRepository, TicketRepository, get_available_counts_by_event, get_checked_in_counts_by_event, get_paid_counts_by_event
from services.booking_service import _expire_pending_bookings_in_session
from services.delivery_service import create_ticket_delivery
from services.event_service import derive_event_runtime_status, serialize_event
from services.qr_service import build_payment_confirmation_payload, build_ticket_payload
from services.seat_service import mark_seat_sold, release_seat
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
        available_map = get_available_counts_by_event(session, [booking.event_id])
        event_snapshot = serialize_event(
            booking.event,
            sold_map.get(booking.event_id, 0),
            checked_map.get(booking.event_id, 0),
            available_count=available_map.get(booking.event_id, 0),
        )
        return (
            {
                "booking_id": booking.id,
                "booking_status": booking.status,
                "amount_kzt": booking.amount_kzt,
                "created_at": booking.created_at,
                "payment_deadline": booking.payment_deadline or booking.expires_at,
                "paid_at": booking.paid_at,
                "ticket_id": booking.ticket.id if booking.ticket else None,
                "customer_email": booking.customer_email,
                "seat": None
                if booking.seat is None
                else {
                    "category": booking.seat.category,
                    "row_label": booking.seat.row_label,
                    "seat_number": booking.seat.seat_number,
                    "price_kzt": booking.seat.price_kzt,
                },
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


def get_payment_confirmation_context(token: str) -> tuple[dict[str, Any] | None, str | None]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        booking = BookingRepository(session).get_by_confirmation_token(token)
        if booking is None:
            return None, "Invalid or expired payment token."

        payment = _ensure_payment(session, booking.id)
        return (
            {
                "booking_id": booking.id,
                "token": token,
                "booking_status": booking.status,
                "customer_email": booking.customer_email,
                "amount_kzt": booking.amount_kzt,
                "payment_deadline": booking.payment_deadline or booking.expires_at,
                "event": {
                    "id": booking.event.id,
                    "title": booking.event.title,
                    "city": booking.event.city,
                    "venue": booking.event.venue,
                    "event_datetime": booking.event.event_datetime,
                },
                "seat": None
                if booking.seat is None
                else {
                    "category": booking.seat.category,
                    "row_label": booking.seat.row_label,
                    "seat_number": booking.seat.seat_number,
                    "price_kzt": booking.seat.price_kzt,
                },
                "payment": {
                    "status": payment.status,
                    "payment_reference": payment.payment_reference,
                    "confirmed_at": payment.confirmed_at,
                },
                "ticket_id": booking.ticket.id if booking.ticket else None,
            },
            None,
        )


def confirm_payment_with_token(token: str) -> tuple[dict[str, Any] | None, list[str]]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        booking = BookingRepository(session).get_by_confirmation_token(token)
        if booking is None:
            return None, ["Invalid or expired payment token."]

        payment = _ensure_payment(session, booking.id)
        if booking.status == "cancelled":
            payment.status = "cancelled"
            return None, ["This payment has been cancelled."]
        if booking.status == "expired":
            payment.status = "failed"
            return None, ["The payment deadline has expired."]
        if booking.status == "paid" and booking.ticket is not None:
            return {"ticket_id": booking.ticket.id, "booking_id": booking.id}, []
        if booking.seat is None:
            return None, ["No seat is attached to this booking."]

        sold_count = get_paid_counts_by_event(session, [booking.event_id]).get(booking.event_id, 0)
        available_count = get_available_counts_by_event(session, [booking.event_id]).get(booking.event_id, 0)
        runtime_status = derive_event_runtime_status(booking.event, sold_count, available_count)
        if runtime_status in {"past", "cancelled"}:
            booking.status = "cancelled"
            payment.status = "cancelled"
            release_seat(session, booking.seat_id)
            return None, ["This event is no longer available for ticketing."]
        if booking.seat.status != "reserved_pending_payment" or booking.seat.booking_id != booking.id:
            return None, ["This seat is no longer reserved for this payment."]

        other_paid = BookingRepository(session).get_paid_for_user_event(booking.user_id, booking.event_id)
        if other_paid is not None and other_paid.id != booking.id:
            booking.status = "cancelled"
            payment.status = "cancelled"
            release_seat(session, booking.seat_id)
            return None, ["A paid ticket already exists for this attendee."]

        ticket = booking.ticket
        if ticket is None:
            ticket = TicketRepository(session).create(
                booking_id=booking.id,
                user_id=booking.user_id,
                event_id=booking.event_id,
                seat_id=booking.seat_id,
                ticket_code=f"ES-{secrets.token_hex(4).upper()}",
                qr_payload="pending",
                category=booking.seat.category,
                row_label=booking.seat.row_label,
                seat_number=booking.seat.seat_number,
                price_kzt=booking.seat.price_kzt,
                status="valid",
            )
            session.flush()
            ticket.qr_payload = build_ticket_payload(ticket.id, ticket.ticket_code)

        booking.status = "paid"
        booking.paid_at = now_local()
        payment.status = "confirmed"
        payment.confirmed_at = booking.paid_at
        mark_seat_sold(session, booking.seat_id, booking.id)
        session.add_all([booking, payment, ticket])
        session.flush()
        create_ticket_delivery(session, ticket)
        return {"ticket_id": ticket.id, "booking_id": booking.id}, []


def cancel_payment(booking_id: int) -> tuple[bool, str]:
    with session_scope() as session:
        booking = BookingRepository(session).get_by_id(booking_id)
        if booking is None:
            return False, "Booking not found."

        payment = _ensure_payment(session, booking.id)
        if booking.status == "paid":
            return False, "Paid bookings cannot be cancelled."
        if booking.status in {"cancelled", "expired"}:
            return False, "This booking is already closed."

        booking.status = "cancelled"
        booking.cancelled_at = now_local()
        payment.status = "cancelled"
        release_seat(session, booking.seat_id)
        session.add_all([booking, payment])
        return True, "Booking cancelled."


def cancel_payment_with_token(token: str) -> tuple[bool, str]:
    with session_scope() as session:
        booking = BookingRepository(session).get_by_confirmation_token(token)
        if booking is None:
            return False, "Invalid or expired payment token."

        payment = _ensure_payment(session, booking.id)
        if booking.status == "paid":
            return False, "This payment has already been confirmed."
        if booking.status in {"cancelled", "expired"}:
            return False, "This booking is already closed."

        booking.status = "cancelled"
        booking.cancelled_at = now_local()
        payment.status = "cancelled"
        release_seat(session, booking.seat_id)
        session.add_all([booking, payment])
        return True, "Payment cancelled and seat released."


def _ensure_payment(session, booking_id: int):
    payment_repo = PaymentSimulationRepository(session)
    payment = payment_repo.get_by_booking_id(booking_id)
    booking = BookingRepository(session).get_by_id(booking_id)
    if booking is None:
        raise ValueError("Booking not found.")
    if booking.payment_confirmation_token is None:
        booking.payment_confirmation_token = secrets.token_urlsafe(24)
        session.add(booking)
    confirmation_url = build_payment_confirmation_payload(booking.payment_confirmation_token)

    if payment is not None:
        payment.qr_payload = confirmation_url
        payment.confirmed_url_path = confirmation_url
        session.add(payment)
        return payment

    payment = payment_repo.create(
        booking_id=booking_id,
        provider="kaspi_sandbox",
        status="pending",
        payment_reference=f"KSP-{secrets.token_hex(4).upper()}",
        qr_payload=confirmation_url,
        confirmed_url_path=confirmation_url,
    )
    session.add(payment)
    return payment
