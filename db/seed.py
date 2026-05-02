from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select

from core.config import settings
from core.security import hash_password, normalize_email
from db.database import Base, get_engine, session_scope
from db.models import Booking, Event, PaymentSimulation, Ticket, User
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
    {"full_name": "Aigerim Bekova", "email": "aigerim.demo@eventsphere.local"},
    {"full_name": "Timur Kassen", "email": "timur.demo@eventsphere.local"},
    {"full_name": "Madina Ospan", "email": "madina.demo@eventsphere.local"},
]

DEFAULT_EVENTS = [
    {
        "title": "Almaty AI & Product Summit",
        "category": "Technology",
        "city": "Almaty",
        "venue": "MOST Hub Almaty",
        "event_datetime": lambda: days_from_now(6, 18, 30),
        "price_kzt": 24000,
        "capacity": 180,
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
        "capacity": 90,
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
        "capacity": 260,
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
        "capacity": 320,
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
        "capacity": 40,
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
        "capacity": 420,
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
        "capacity": 110,
        "image_url": "https://images.unsplash.com/photo-1511795409834-ef04bbd61622?auto=format&fit=crop&w=1400&q=80",
        "description": (
            "A community meetup for analytics engineers and data leads covering practical warehousing workflows, "
            "career stories, and team learnings from local product companies."
        ),
    },
]

SAMPLE_BOOKINGS = [
    ("user@eventsphere.local", "UX Sprint Workshop: Service Design in Practice", "valid"),
    ("aigerim.demo@eventsphere.local", "Almaty AI & Product Summit", "valid"),
    ("timur.demo@eventsphere.local", "Astana Startup Capital Breakfast", "valid"),
    ("madina.demo@eventsphere.local", "Silk Road Live Sessions", "valid"),
    ("aigerim.demo@eventsphere.local", "Almaty Data Leaders Meetup", "used"),
]


def initialize_database() -> None:
    Base.metadata.create_all(bind=get_engine())
    with session_scope() as session:
        _seed_users(session)
        _seed_events(session)
        _seed_demo_bookings(session)


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
                    password_hash=hash_password("DemoUser123!"),
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
            session.add(
                Event(
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
            )
            continue

        if existing.event_datetime < current_time and not existing.tickets:
            existing.event_datetime = event_datetime
        existing.description = event_data["description"]
        existing.category = event_data["category"]
        existing.city = event_data["city"]
        existing.venue = event_data["venue"]
        existing.price_kzt = event_data["price_kzt"]
        existing.capacity = event_data["capacity"]
        existing.image_url = event_data["image_url"]
        if existing.status not in {"cancelled"}:
            existing.status = "scheduled"
    session.flush()


def _seed_demo_bookings(session) -> None:
    for email, event_title, ticket_status in SAMPLE_BOOKINGS:
        user = session.scalar(select(User).where(User.email == email))
        event = session.scalar(select(Event).where(Event.title == event_title))
        if user is None or event is None:
            continue

        existing_paid = session.scalar(
            select(Booking).where(Booking.user_id == user.id, Booking.event_id == event.id, Booking.status == "paid")
        )
        if existing_paid is not None:
            continue

        created_at = min(event.event_datetime - timedelta(days=2), now_local())
        booking = Booking(
            user_id=user.id,
            event_id=event.id,
            status="paid",
            amount_kzt=event.price_kzt,
            created_at=created_at,
            expires_at=created_at + timedelta(minutes=settings.payment_window_minutes),
            paid_at=created_at + timedelta(minutes=5),
        )
        session.add(booking)
        session.flush()

        payment = PaymentSimulation(
            booking_id=booking.id,
            provider=settings.payment_provider,
            status="confirmed",
            payment_reference=f"KSP-{secrets.token_hex(4).upper()}",
            qr_payload=f"{settings.public_app_url}?route=payment&booking_id={booking.id}",
            created_at=created_at,
            confirmed_at=booking.paid_at,
        )
        session.add(payment)
        session.flush()

        ticket = Ticket(
            booking_id=booking.id,
            user_id=user.id,
            event_id=event.id,
            ticket_code=f"ES-{secrets.token_hex(4).upper()}",
            qr_payload=f"{settings.public_app_url}?route=ticket&ticket_id=0",
            status=ticket_status,
            created_at=booking.paid_at or created_at,
            checked_in_at=(event.event_datetime + timedelta(minutes=10)) if ticket_status == "used" else None,
        )
        session.add(ticket)
        session.flush()
        ticket.qr_payload = f"{settings.public_app_url}?route=ticket&ticket_id={ticket.id}&code={ticket.ticket_code}"
