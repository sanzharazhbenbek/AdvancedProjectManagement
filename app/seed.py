from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Event, User
from .security import hash_password, normalize_email


DEFAULT_USERS = [
    {
        "full_name": "System Administrator",
        "email": "admin@eventsphere.local",
        "password": "Admin123!",
        "role": "admin",
    },
    {
        "full_name": "Event Operations Lead",
        "email": "organizer@eventsphere.local",
        "password": "Organizer123!",
        "role": "organizer",
    },
    {
        "full_name": "EventSphere Member",
        "email": "user@eventsphere.local",
        "password": "User123!",
        "role": "user",
    },
]

DEFAULT_EVENTS = [
    {
        "title": "Nomad Tech Night",
        "category": "Technology",
        "venue": "Tech Garden Hall",
        "city": "Almaty",
        "description": (
            "An evening meetup for startup founders, developers, and students with short talks, "
            "networking, and open discussion."
        ),
        "ticket_price": 12000,
        "capacity": 120,
        "days_from_now": 4,
        "image_url": "https://images.unsplash.com/photo-1511578314322-379afb476865?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "title": "Campus Creator Fest",
        "category": "Student Club",
        "venue": "Main Auditorium",
        "city": "Almaty",
        "description": (
            "A student-led event with performances, club showcases, and small creative workshops "
            "for the campus community."
        ),
        "ticket_price": 5000,
        "capacity": 240,
        "days_from_now": 8,
        "image_url": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "title": "Startup Breakfast Sprint",
        "category": "Business",
        "venue": "Skyline Coworking",
        "city": "Astana",
        "description": (
            "A compact morning session for founders and investors with quick pitches, curated introductions, "
            "and a practical talk on early traction."
        ),
        "ticket_price": 18000,
        "capacity": 60,
        "days_from_now": 12,
        "image_url": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=1200&q=80",
    },
]


def seed_default_users(session: Session) -> None:
    users_by_email: dict[str, User] = {}
    for item in DEFAULT_USERS:
        email = normalize_email(item["email"])
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                full_name=item["full_name"],
                email=email,
                password_hash=hash_password(item["password"]),
                role=item["role"],
                is_active=True,
            )
            session.add(user)
            session.flush()
        users_by_email[email] = user

    organizer = users_by_email["organizer@eventsphere.local"]
    now = datetime.now().replace(second=0, microsecond=0)
    for item in DEFAULT_EVENTS:
        existing_event = session.scalar(
            select(Event.id).where(Event.organizer_id == organizer.id, Event.title == item["title"])
        )
        if existing_event is not None:
            continue

        event_day = now + timedelta(days=item["days_from_now"])
        session.add(
            Event(
                organizer_id=organizer.id,
                organizer_name=organizer.full_name,
                title=item["title"],
                category=item["category"],
                venue=item["venue"],
                city=item["city"],
                description=item["description"],
                event_date=event_day.replace(hour=19, minute=0),
                ticket_price=float(item["ticket_price"]),
                capacity=int(item["capacity"]),
                image_url=item["image_url"],
            )
        )

    session.commit()
