from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    events: Mapped[list["Event"]] = relationship(back_populates="organizer")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="user")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    venue: Mapped[str] = mapped_column(String(160), nullable=False)
    event_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    price_kzt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organizer: Mapped[User] = relationship(back_populates="events")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="event")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="event")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_payment")
    amount_kzt: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="bookings")
    event: Mapped[Event] = relationship(back_populates="bookings")
    ticket: Mapped["Ticket | None"] = relationship(back_populates="booking", uselist=False)
    payment: Mapped["PaymentSimulation | None"] = relationship(back_populates="booking", uselist=False)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("booking_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    ticket_code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="ticket")
    user: Mapped[User] = relationship(back_populates="tickets")
    event: Mapped[Event] = relationship(back_populates="tickets")


class PaymentSimulation(Base):
    __tablename__ = "payment_simulations"
    __table_args__ = (UniqueConstraint("booking_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="kaspi_sandbox")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    payment_reference: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="payment")
