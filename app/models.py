from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    events: Mapped[list["Event"]] = relationship(back_populates="organizer")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="purchaser")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    organizer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    venue: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ticket_price: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    organizer: Mapped[User | None] = relationship(back_populates="events")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    purchaser_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    purchaser_name: Mapped[str] = mapped_column(String(120), nullable=False)
    purchaser_email: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(60), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(60), nullable=False, default="Confirmed")
    payment_reference: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    payment_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ticket_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    ticket_status: Mapped[str] = mapped_column(String(30), nullable=False, default="Active")
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    event: Mapped[Event] = relationship(back_populates="tickets")
    purchaser: Mapped[User | None] = relationship(back_populates="tickets")
    payments: Mapped[list["PaymentRecord"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_reference: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Confirmed")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KZT")
    payer_identifier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confirmation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    ticket: Mapped[Ticket] = relationship(back_populates="payments")
