from __future__ import annotations

import secrets
from typing import Any

from db.database import session_scope
from db.repositories import (
    BookingRepository,
    PaymentSimulationRepository,
    TicketRepository,
    get_available_counts_by_event,
    get_checked_in_counts_by_event,
    get_paid_counts_by_event,
)
from services.booking_service import _expire_pending_bookings_in_session
from services.delivery_service import create_ticket_delivery
from services.event_service import derive_event_runtime_status, serialize_event
from services.qr_service import build_payment_confirmation_payload, build_ticket_payload
from services.seat_service import mark_seat_sold, release_seat
from utils.date_utils import now_local


def get_payment_context(booking_id: int) -> tuple[dict[str, Any] | None, str | None]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        requested_booking = BookingRepository(session).get_by_id(booking_id)
        if requested_booking is None:
            return None, "Booking not found."

        group_bookings = _load_group_bookings(session, requested_booking)
        primary_booking = _select_primary_booking(group_bookings, requested_booking)
        payment = _ensure_payment(session, primary_booking.id)
        sold_map = get_paid_counts_by_event(session, [primary_booking.event_id])
        checked_map = get_checked_in_counts_by_event(session, [primary_booking.event_id])
        available_map = get_available_counts_by_event(session, [primary_booking.event_id])
        event_snapshot = serialize_event(
            primary_booking.event,
            sold_map.get(primary_booking.event_id, 0),
            checked_map.get(primary_booking.event_id, 0),
            available_count=available_map.get(primary_booking.event_id, 0),
        )
        ticket_ids = [booking.ticket.id for booking in group_bookings if booking.ticket is not None]
        return (
            {
                "booking_id": primary_booking.id,
                "booking_status": primary_booking.status,
                "ticket_count": len(group_bookings),
                "ticket_ids": ticket_ids,
                "ticket_id": ticket_ids[0] if ticket_ids else None,
                "amount_kzt": sum(booking.amount_kzt for booking in group_bookings),
                "created_at": primary_booking.created_at,
                "payment_deadline": primary_booking.payment_deadline or primary_booking.expires_at,
                "paid_at": primary_booking.paid_at,
                "customer_email": primary_booking.customer_email,
                "seats": _serialize_group_seats(group_bookings),
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

        group_bookings = _load_group_bookings(session, booking)
        primary_booking = _select_primary_booking(group_bookings, booking)
        payment = _ensure_payment(session, primary_booking.id)
        ticket_ids = [group_booking.ticket.id for group_booking in group_bookings if group_booking.ticket is not None]
        return (
            {
                "booking_id": primary_booking.id,
                "token": token,
                "booking_status": primary_booking.status,
                "customer_email": primary_booking.customer_email,
                "amount_kzt": sum(group_booking.amount_kzt for group_booking in group_bookings),
                "ticket_count": len(group_bookings),
                "ticket_ids": ticket_ids,
                "ticket_id": ticket_ids[0] if ticket_ids else None,
                "payment_deadline": primary_booking.payment_deadline or primary_booking.expires_at,
                "event": {
                    "id": primary_booking.event.id,
                    "title": primary_booking.event.title,
                    "city": primary_booking.event.city,
                    "venue": primary_booking.event.venue,
                    "event_datetime": primary_booking.event.event_datetime,
                },
                "seats": _serialize_group_seats(group_bookings),
                "payment": {
                    "status": payment.status,
                    "payment_reference": payment.payment_reference,
                    "confirmed_at": payment.confirmed_at,
                },
            },
            None,
        )


def confirm_payment_with_token(token: str) -> tuple[dict[str, Any] | None, list[str]]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        token_booking = BookingRepository(session).get_by_confirmation_token(token)
        if token_booking is None:
            return None, ["Invalid or expired payment token."]

        group_bookings = _load_group_bookings(session, token_booking)
        primary_booking = _select_primary_booking(group_bookings, token_booking)
        payment = _ensure_payment(session, primary_booking.id)

        if primary_booking.status == "cancelled":
            payment.status = "cancelled"
            session.add(payment)
            return None, ["This payment has been cancelled."]
        if primary_booking.status == "expired":
            payment.status = "failed"
            session.add(payment)
            return None, ["The payment deadline has expired."]

        ticket_ids = [booking.ticket.id for booking in group_bookings if booking.ticket is not None]
        if primary_booking.status == "paid" and len(ticket_ids) == len(group_bookings):
            return {
                "ticket_id": ticket_ids[0] if ticket_ids else None,
                "ticket_ids": ticket_ids,
                "ticket_count": len(ticket_ids),
                "booking_id": primary_booking.id,
            }, []

        sold_count = get_paid_counts_by_event(session, [primary_booking.event_id]).get(primary_booking.event_id, 0)
        available_count = get_available_counts_by_event(session, [primary_booking.event_id]).get(primary_booking.event_id, 0)
        runtime_status = derive_event_runtime_status(primary_booking.event, sold_count, available_count)
        if runtime_status in {"past", "cancelled"}:
            _close_pending_group(session, group_bookings, status="cancelled", payment_status="cancelled")
            return None, ["This event is no longer available for ticketing."]

        for booking in group_bookings:
            if booking.status not in {"pending_payment", "paid"}:
                return None, ["This booking group can no longer be confirmed."]
            if booking.seat is None:
                return None, ["One of the selected seats is missing from this booking."]
            if booking.status == "pending_payment" and (
                booking.seat.status != "reserved_pending_payment" or booking.seat.booking_id != booking.id
            ):
                return None, ["One of the selected seats is no longer reserved for this payment."]

        paid_at = now_local()
        created_ticket_ids: list[int] = []
        for booking in group_bookings:
            ticket = booking.ticket
            if ticket is None:
                ticket = TicketRepository(session).create(
                    booking_id=booking.id,
                    user_id=booking.user_id,
                    event_id=booking.event_id,
                    seat_id=booking.seat_id,
                    ticket_code=f"ES-{secrets.token_hex(4).upper()}",
                    qr_payload="pending",
                    category=booking.seat.category if booking.seat else None,
                    row_label=booking.seat.row_label if booking.seat else None,
                    seat_number=booking.seat.seat_number if booking.seat else None,
                    price_kzt=booking.seat.price_kzt if booking.seat else booking.amount_kzt,
                    status="valid",
                )
                session.flush()
                ticket.qr_payload = build_ticket_payload(ticket.id, ticket.ticket_code)

            booking.status = "paid"
            booking.paid_at = paid_at
            mark_seat_sold(session, booking.seat_id, booking.id)
            session.add_all([booking, ticket])
            session.flush()
            create_ticket_delivery(session, ticket)
            created_ticket_ids.append(ticket.id)

        payment.status = "confirmed"
        payment.confirmed_at = paid_at
        session.add(payment)
        return {
            "ticket_id": created_ticket_ids[0] if created_ticket_ids else None,
            "ticket_ids": created_ticket_ids,
            "ticket_count": len(created_ticket_ids),
            "booking_id": primary_booking.id,
        }, []


def cancel_payment(booking_id: int) -> tuple[bool, str]:
    with session_scope() as session:
        requested_booking = BookingRepository(session).get_by_id(booking_id)
        if requested_booking is None:
            return False, "Booking not found."

        group_bookings = _load_group_bookings(session, requested_booking)
        primary_booking = _select_primary_booking(group_bookings, requested_booking)
        payment = _ensure_payment(session, primary_booking.id)
        if primary_booking.status == "paid":
            return False, "Paid bookings cannot be cancelled."
        if primary_booking.status in {"cancelled", "expired"}:
            return False, "This booking is already closed."

        _close_pending_group(session, group_bookings, status="cancelled", payment_status="cancelled")
        session.add(payment)
        return True, "Booking cancelled."


def cancel_payment_with_token(token: str) -> tuple[bool, str]:
    with session_scope() as session:
        token_booking = BookingRepository(session).get_by_confirmation_token(token)
        if token_booking is None:
            return False, "Invalid or expired payment token."

        group_bookings = _load_group_bookings(session, token_booking)
        primary_booking = _select_primary_booking(group_bookings, token_booking)
        payment = _ensure_payment(session, primary_booking.id)
        if primary_booking.status == "paid":
            return False, "This payment has already been confirmed."
        if primary_booking.status in {"cancelled", "expired"}:
            return False, "This booking is already closed."

        _close_pending_group(session, group_bookings, status="cancelled", payment_status="cancelled")
        session.add(payment)
        return True, "Payment cancelled and seats released."


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


def _load_group_bookings(session, booking) -> list:
    if booking.booking_group_token:
        bookings = BookingRepository(session).list_for_group_token(booking.booking_group_token)
        if bookings:
            return bookings
    return [booking]


def _select_primary_booking(bookings: list, fallback):
    for booking in bookings:
        if booking.payment_confirmation_token or booking.payment is not None:
            return booking
    return fallback if fallback in bookings else sorted(bookings, key=lambda item: (item.created_at, item.id))[0]


def _serialize_group_seats(group_bookings: list) -> list[dict[str, Any]]:
    return [
        {
            "seat_id": booking.seat_id,
            "category": booking.seat.category if booking.seat else None,
            "row_label": booking.seat.row_label if booking.seat else None,
            "seat_number": booking.seat.seat_number if booking.seat else None,
            "price_kzt": booking.seat.price_kzt if booking.seat else booking.amount_kzt,
            "ticket_id": booking.ticket.id if booking.ticket else None,
        }
        for booking in sorted(group_bookings, key=lambda item: ((item.seat.row_label if item.seat else ""), (item.seat.seat_number if item.seat else 0), item.id))
    ]


def _close_pending_group(session, group_bookings: list, *, status: str, payment_status: str) -> None:
    timestamp = now_local()
    primary_booking = _select_primary_booking(group_bookings, group_bookings[0])
    if primary_booking.payment is not None:
        primary_booking.payment.status = payment_status
        session.add(primary_booking.payment)

    for booking in group_bookings:
        if booking.status == "paid":
            continue
        booking.status = status
        booking.cancelled_at = timestamp if status == "cancelled" else booking.cancelled_at
        release_seat(session, booking.seat_id)
        session.add(booking)
