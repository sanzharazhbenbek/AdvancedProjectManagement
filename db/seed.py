from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select

from core.config import settings
from core.security import hash_password, normalize_email
from db.database import Base, get_engine, session_scope
from db.migrations import migrate_database_if_needed
from db.models import Booking, EmailLog, Event, PaymentSimulation, Seat, Ticket, User
from db.repositories import EmailLogRepository, SeatRepository, TicketRepository
from services.delivery_service import create_ticket_delivery
from services.qr_service import build_payment_confirmation_payload, build_ticket_payload
from services.seat_service import mark_seat_sold, reserve_seat_for_booking, serialize_seat, sync_event_seats
from utils.date_utils import days_from_now, now_local
from utils.formatters import slugify


DEFAULT_USERS = [
    {
        "full_name": "System Administrator",
        "email": "admin@eventsphere.local",
        "password": "Admin123!",
        "role": "admin",
    },
    {
        "full_name": "Aruzhan Sadykova",
        "email": "organizer@eventsphere.local",
        "password": "Organizer123!",
        "role": "organizer",
    },
    {
        "full_name": "Dias Nurgaliyev",
        "email": "user@eventsphere.local",
        "password": "User123!",
        "role": "user",
    },
]

EXTRA_ATTENDEES = [
    {"full_name": "Aigerim Bekova", "email": "aigerim.bekova@eventsphere.local"},
    {"full_name": "Timur Kassen", "email": "timur.kassen@eventsphere.local"},
    {"full_name": "Madina Ospan", "email": "madina.ospan@eventsphere.local"},
]

DEFAULT_EVENTS = [
    {
        "title": "Almaty AI & Product Summit",
        "category": "Technology",
        "city": "Almaty",
        "venue": "MOST Hub Almaty",
        "event_datetime": lambda: days_from_now(6, 18, 30),
        "price_kzt": 24000,
        "capacity": 160,
        "image_url": "https://images.unsplash.com/photo-1511578314322-379afb476865?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A focused evening summit for product leaders, startup operators, and AI builders discussing applied "
            "automation, local market case studies, and practical go-to-market lessons in Kazakhstan."
        ),
    },
    {
        "title": "Astana Startup Capital Breakfast",
        "category": "Business",
        "city": "Astana",
        "venue": "Talan Towers Conference Lounge",
        "event_datetime": lambda: days_from_now(10, 9, 0),
        "price_kzt": 18000,
        "capacity": 60,
        "image_url": "https://images.unsplash.com/photo-1515169067868-5387ec356754?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A compact founder breakfast featuring investor office hours, quick traction reviews, and sharp "
            "conversations for early-stage teams preparing their next growth sprint."
        ),
    },
    {
        "title": "NU Creative Club Night",
        "category": "University Club",
        "city": "Astana",
        "venue": "Nazarbayev University Main Atrium",
        "event_datetime": lambda: days_from_now(14, 18, 0),
        "price_kzt": 4500,
        "capacity": 160,
        "image_url": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "An energetic campus showcase with student club activations, acoustic sets, live art corners, and a "
            "late-evening social designed to help new members discover communities on campus."
        ),
    },
    {
        "title": "Silk Road Live Sessions",
        "category": "Music",
        "city": "Shymkent",
        "venue": "Arbat Open Air Stage",
        "event_datetime": lambda: days_from_now(20, 20, 0),
        "price_kzt": 16000,
        "capacity": 160,
        "image_url": "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A live outdoor concert featuring rising Kazakh indie acts, visual stage design, and a food-market "
            "experience built around a warm summer city-night atmosphere."
        ),
    },
    {
        "title": "UX Sprint Workshop: Service Design in Practice",
        "category": "Workshop",
        "city": "Almaty",
        "venue": "SmArt.Point Workshop Studio",
        "event_datetime": lambda: days_from_now(4, 11, 0),
        "price_kzt": 30000,
        "capacity": 42,
        "image_url": "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A hands-on workshop for designers and operations teams covering journey mapping, service blueprinting, "
            "and facilitation patterns that translate directly into stronger event experiences."
        ),
    },
    {
        "title": "Kazakhstan Future of Retail Conference",
        "category": "Conference",
        "city": "Astana",
        "venue": "EXPO Congress Center",
        "event_datetime": lambda: days_from_now(32, 10, 0),
        "price_kzt": 52000,
        "capacity": 160,
        "image_url": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A one-day industry conference on omnichannel retail, digital payments, logistics, and consumer data "
            "trends with operator-led talks and executive networking across the region."
        ),
    },
    {
        "title": "Almaty Data Leaders Meetup",
        "category": "Technology",
        "city": "Almaty",
        "venue": "Satbayev University Tech Hall",
        "event_datetime": lambda: days_from_now(-7, 19, 0),
        "price_kzt": 8000,
        "capacity": 60,
        "image_url": "https://images.unsplash.com/photo-1511795409834-ef04bbd61622?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A community meetup for analytics engineers and data leads covering practical warehousing workflows, "
            "career stories, and team learnings from local product companies."
        ),
    },
]

INITIAL_BOOKINGS = [
    ("user@eventsphere.local", "UX Sprint Workshop: Service Design in Practice", "valid"),
    ("aigerim.bekova@eventsphere.local", "Almaty AI & Product Summit", "valid"),
    ("timur.kassen@eventsphere.local", "Astana Startup Capital Breakfast", "valid"),
    ("madina.ospan@eventsphere.local", "Silk Road Live Sessions", "valid"),
    ("aigerim.bekova@eventsphere.local", "Almaty Data Leaders Meetup", "used"),
]

LEGACY_ATTENDEE_EMAILS = {
    "aigerim.demo@eventsphere.local": "aigerim.bekova@eventsphere.local",
    "timur.demo@eventsphere.local": "timur.kassen@eventsphere.local",
    "madina.demo@eventsphere.local": "madina.ospan@eventsphere.local",
}


def initialize_database() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tickets_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    migrate_database_if_needed()
    Base.metadata.create_all(bind=get_engine())
    with session_scope() as session:
        seed_database_if_empty(session)
        _backfill_legacy_records(session)
        _seed_initial_bookings(session)


def seed_database_if_empty(session) -> None:
    _seed_users(session)
    _seed_events(session)


def _seed_users(session) -> None:
    for user_data in DEFAULT_USERS:
        email = normalize_email(user_data["email"])
        existing = session.scalar(select(User).where(User.email == email))
        if existing is None:
            session.add(
                User(
                    full_name=user_data["full_name"],
                    email=email,
                    password_hash=hash_password(user_data["password"]),
                    role=user_data["role"],
                    is_active=True,
                )
            )

    for attendee in EXTRA_ATTENDEES:
        email = normalize_email(attendee["email"])
        existing = session.scalar(select(User).where(User.email == email))
        if existing is None:
            session.add(
                User(
                    full_name=attendee["full_name"],
                    email=email,
                    password_hash=hash_password("Attendee123!"),
                    role="user",
                    is_active=True,
                )
            )
    session.flush()


def _seed_events(session) -> None:
    organizer = session.scalar(select(User).where(User.email == "organizer@eventsphere.local"))
    if organizer is None:
        return

    current_time = now_local()
    for event_data in DEFAULT_EVENTS:
        slug = slugify(event_data["title"])
        existing = session.scalar(select(Event).where(Event.slug == slug))
        event_datetime = event_data["event_datetime"]()
        if existing is None:
            existing = Event(
                title=event_data["title"],
                slug=slug,
                description=event_data["description"],
                category=event_data["category"],
                city=event_data["city"],
                venue=event_data["venue"],
                event_datetime=event_datetime,
                price_kzt=event_data["price_kzt"],
                capacity=event_data["capacity"],
                image_url=event_data["image_url"],
                organizer_id=organizer.id,
                status="scheduled",
            )
            session.add(existing)
            session.flush()
        else:
            if existing.event_datetime < current_time and not existing.tickets:
                existing.event_datetime = event_datetime
            existing.description = event_data["description"]
            existing.category = event_data["category"]
            existing.city = event_data["city"]
            existing.venue = event_data["venue"]
            existing.price_kzt = event_data["price_kzt"]
            existing.capacity = event_data["capacity"]
            existing.image_url = event_data["image_url"]
            if existing.status != "cancelled":
                existing.status = "scheduled"

        sync_event_seats(session, existing, mode="seed")
    session.flush()


def _backfill_legacy_records(session) -> None:
    for old_email, new_email in LEGACY_ATTENDEE_EMAILS.items():
        legacy_user = session.scalar(select(User).where(User.email == old_email))
        replacement_user = session.scalar(select(User).where(User.email == new_email))
        if legacy_user is not None and replacement_user is None:
            legacy_user.email = new_email
            session.add(legacy_user)

    for booking in session.scalars(select(Booking)).all():
        if booking.customer_email in LEGACY_ATTENDEE_EMAILS:
            booking.customer_email = LEGACY_ATTENDEE_EMAILS[booking.customer_email]
        if not booking.customer_email and booking.user_id:
            user = session.get(User, booking.user_id)
            booking.customer_email = user.email if user else None
        if booking.payment_deadline is None:
            booking.payment_deadline = booking.expires_at
        if not booking.payment_confirmation_token:
            booking.payment_confirmation_token = secrets.token_urlsafe(24)
        session.add(booking)

    session.flush()

    for event in session.scalars(select(Event)).all():
        seats = SeatRepository(session).list_for_event(event.id)
        if not seats:
            sync_event_seats(session, event, mode="seed")

    session.flush()

    for payment in session.scalars(select(PaymentSimulation)).all():
        booking = session.get(Booking, payment.booking_id)
        if booking is None or not booking.payment_confirmation_token:
            continue
        if payment.provider == "kaspi_sandbox":
            payment.provider = settings.payment_provider
        payment.qr_payload = build_payment_confirmation_payload(booking.payment_confirmation_token)
        payment.confirmed_url_path = payment.qr_payload
        session.add(payment)

    for email_log in session.scalars(select(EmailLog)).all():
        if email_log.recipient_email in LEGACY_ATTENDEE_EMAILS:
            email_log.recipient_email = LEGACY_ATTENDEE_EMAILS[email_log.recipient_email]
        if email_log.status == "simulated":
            email_log.status = "delivered"
        session.add(email_log)

    session.flush()

    for booking in session.scalars(select(Booking).order_by(Booking.created_at.asc())).all():
        if booking.status == "pending_payment" and booking.seat_id is None:
            booking.status = "cancelled"
            booking.cancelled_at = now_local()
            if booking.payment is not None:
                booking.payment.status = "cancelled"
            session.add(booking)

        if booking.status == "paid" and booking.seat_id is None:
            seat = _first_available_seat(session, booking.event_id)
            if seat is not None:
                booking.seat_id = seat.id
                mark_seat_sold(session, seat.id, booking.id)
                session.add(booking)
        elif booking.status == "pending_payment" and booking.seat_id is not None:
            reserve_seat_for_booking(session, booking.seat_id, booking.id)
        elif booking.status in {"cancelled", "expired"} and booking.seat_id is not None:
            seat = session.get(Seat, booking.seat_id)
            if seat and seat.status != "sold":
                seat.status = "available"
                seat.booking_id = None
                session.add(seat)

    session.flush()

    for ticket in TicketRepository(session).list_all():
        if ticket.seat_id is None and ticket.booking and ticket.booking.seat_id:
            ticket.seat_id = ticket.booking.seat_id
        if ticket.seat_id:
            seat = session.get(Seat, ticket.seat_id)
            if seat is not None:
                ticket.category = seat.category
                ticket.row_label = seat.row_label
                ticket.seat_number = seat.seat_number
                ticket.price_kzt = seat.price_kzt
                mark_seat_sold(session, seat.id, ticket.booking_id)
        if not ticket.qr_payload or ticket.qr_payload == "pending":
            ticket.qr_payload = build_ticket_payload(ticket.id, ticket.ticket_code)
        ticket.ticket_file_path = None
        create_ticket_delivery(session, ticket)
        session.add(ticket)


def _seed_initial_bookings(session) -> None:
    for email, event_title, ticket_status in INITIAL_BOOKINGS:
        user = session.scalar(select(User).where(User.email == email))
        event = session.scalar(select(Event).where(Event.title == event_title))
        if user is None or event is None:
            continue

        existing_paid = session.scalar(
            select(Booking).where(Booking.user_id == user.id, Booking.event_id == event.id, Booking.status == "paid")
        )
        if existing_paid is not None:
            continue

        seat = _first_available_seat(session, event.id)
        if seat is None:
            continue

        created_at = min(event.event_datetime - timedelta(days=2), now_local())
        confirmation_token = secrets.token_urlsafe(24)
        booking = Booking(
            user_id=user.id,
            event_id=event.id,
            seat_id=seat.id,
            status="paid",
            amount_kzt=seat.price_kzt,
            customer_email=user.email,
            created_at=created_at,
            expires_at=created_at + timedelta(minutes=settings.payment_window_minutes),
            payment_deadline=created_at + timedelta(minutes=settings.payment_window_minutes),
            payment_confirmation_token=confirmation_token,
            paid_at=created_at + timedelta(minutes=5),
        )
        session.add(booking)
        session.flush()

        payment_url = build_payment_confirmation_payload(confirmation_token)
        payment = PaymentSimulation(
            booking_id=booking.id,
            provider=settings.payment_provider,
            status="confirmed",
            payment_reference=f"KSP-{secrets.token_hex(4).upper()}",
            qr_payload=payment_url,
            confirmed_url_path=payment_url,
            created_at=created_at,
            confirmed_at=booking.paid_at,
        )
        session.add(payment)
        session.flush()

        mark_seat_sold(session, seat.id, booking.id)

        ticket = Ticket(
            booking_id=booking.id,
            user_id=user.id,
            event_id=event.id,
            seat_id=seat.id,
            ticket_code=f"ES-{secrets.token_hex(4).upper()}",
            qr_payload="pending",
            category=seat.category,
            row_label=seat.row_label,
            seat_number=seat.seat_number,
            price_kzt=seat.price_kzt,
            status=ticket_status,
            created_at=booking.paid_at or created_at,
            checked_in_at=(event.event_datetime + timedelta(minutes=10)) if ticket_status == "used" else None,
        )
        session.add(ticket)
        session.flush()
        ticket.qr_payload = build_ticket_payload(ticket.id, ticket.ticket_code)
        create_ticket_delivery(session, ticket)

    session.flush()


def _first_available_seat(session, event_id: int) -> Seat | None:
    return session.scalar(
        select(Seat)
        .where(Seat.event_id == event_id, Seat.status == "available")
        .order_by(Seat.price_kzt.asc(), Seat.row_label.asc(), Seat.seat_number.asc())
    )
