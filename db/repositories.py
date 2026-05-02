from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from db.models import Booking, EmailLog, Event, PaymentSimulation, Seat, Ticket, User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int | None) -> User | None:
        if user_id is None:
            return None
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.created_at.desc(), User.full_name.asc())
        return list(self.session.scalars(stmt).all())

    def count_all(self) -> int:
        return int(self.session.scalar(select(func.count(User.id))) or 0)

    def count_by_role(self, role: str) -> int:
        return int(self.session.scalar(select(func.count(User.id)).where(User.role == role)) or 0)

    def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self.session.add(user)
        self.session.flush()
        return user


class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def base_query(self) -> Select[tuple[Event]]:
        return select(Event).options(joinedload(Event.organizer))

    def get_by_id(self, event_id: int | None) -> Event | None:
        if event_id is None:
            return None
        stmt = self.base_query().where(Event.id == event_id)
        return self.session.scalar(stmt)

    def get_by_slug(self, slug: str) -> Event | None:
        stmt = self.base_query().where(Event.slug == slug)
        return self.session.scalar(stmt)

    def list_all(self) -> list[Event]:
        stmt = self.base_query().order_by(Event.event_datetime.asc(), Event.title.asc())
        return list(self.session.scalars(stmt).unique().all())

    def list_by_organizer(self, organizer_id: int) -> list[Event]:
        stmt = self.base_query().where(Event.organizer_id == organizer_id).order_by(Event.event_datetime.asc())
        return list(self.session.scalars(stmt).unique().all())

    def create(self, **kwargs) -> Event:
        event = Event(**kwargs)
        self.session.add(event)
        self.session.flush()
        return event


class BookingRepository:
    def __init__(self, session: Session):
        self.session = session

    def _query(self):
        return select(Booking).options(
            joinedload(Booking.user),
            joinedload(Booking.event).joinedload(Event.organizer),
            joinedload(Booking.payment),
            joinedload(Booking.ticket).joinedload(Ticket.seat),
            joinedload(Booking.seat),
        )

    def get_by_id(self, booking_id: int | None) -> Booking | None:
        if booking_id is None:
            return None
        return self.session.scalar(self._query().where(Booking.id == booking_id))

    def get_by_confirmation_token(self, token: str) -> Booking | None:
        return self.session.scalar(self._query().where(Booking.payment_confirmation_token == token))

    def list_all(self) -> list[Booking]:
        stmt = self._query().order_by(Booking.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def list_for_user(self, user_id: int) -> list[Booking]:
        stmt = self._query().where(Booking.user_id == user_id).order_by(Booking.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def list_recent(self, limit: int = 10) -> list[Booking]:
        stmt = self._query().order_by(Booking.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).unique().all())

    def list_for_events(self, event_ids: Sequence[int]) -> list[Booking]:
        if not event_ids:
            return []
        stmt = self._query().where(Booking.event_id.in_(event_ids)).order_by(Booking.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def get_paid_for_user_event(self, user_id: int, event_id: int) -> Booking | None:
        stmt = self._query().where(Booking.user_id == user_id, Booking.event_id == event_id, Booking.status == "paid")
        return self.session.scalar(stmt)

    def get_pending_for_user_event(self, user_id: int, event_id: int) -> Booking | None:
        stmt = (
            self._query()
            .where(Booking.user_id == user_id, Booking.event_id == event_id, Booking.status == "pending_payment")
            .order_by(Booking.created_at.desc())
        )
        return self.session.scalar(stmt)

    def create(self, **kwargs) -> Booking:
        booking = Booking(**kwargs)
        self.session.add(booking)
        self.session.flush()
        return booking


class TicketRepository:
    def __init__(self, session: Session):
        self.session = session

    def _query(self):
        return select(Ticket).options(
            joinedload(Ticket.user),
            joinedload(Ticket.event).joinedload(Event.organizer),
            joinedload(Ticket.booking).joinedload(Booking.payment),
            joinedload(Ticket.seat),
        )

    def get_by_id(self, ticket_id: int | None) -> Ticket | None:
        if ticket_id is None:
            return None
        return self.session.scalar(self._query().where(Ticket.id == ticket_id))

    def get_by_code(self, ticket_code: str) -> Ticket | None:
        return self.session.scalar(self._query().where(Ticket.ticket_code == ticket_code))

    def get_by_booking_id(self, booking_id: int) -> Ticket | None:
        return self.session.scalar(self._query().where(Ticket.booking_id == booking_id))

    def list_all(self) -> list[Ticket]:
        stmt = self._query().order_by(Ticket.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def list_for_user(self, user_id: int) -> list[Ticket]:
        stmt = self._query().where(Ticket.user_id == user_id).order_by(Ticket.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def list_for_event(self, event_id: int) -> list[Ticket]:
        stmt = self._query().where(Ticket.event_id == event_id).order_by(Ticket.created_at.asc())
        return list(self.session.scalars(stmt).unique().all())

    def create(self, **kwargs) -> Ticket:
        ticket = Ticket(**kwargs)
        self.session.add(ticket)
        self.session.flush()
        return ticket


class SeatRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, seat_id: int | None) -> Seat | None:
        if seat_id is None:
            return None
        stmt = select(Seat).options(joinedload(Seat.event)).where(Seat.id == seat_id)
        return self.session.scalar(stmt)

    def list_for_event(self, event_id: int) -> list[Seat]:
        stmt = (
            select(Seat)
            .where(Seat.event_id == event_id)
            .order_by(Seat.category.asc(), Seat.row_label.asc(), Seat.seat_number.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_for_events(self, event_ids: Sequence[int]) -> list[Seat]:
        if not event_ids:
            return []
        stmt = (
            select(Seat)
            .where(Seat.event_id.in_(event_ids))
            .order_by(Seat.event_id.asc(), Seat.category.asc(), Seat.row_label.asc(), Seat.seat_number.asc())
        )
        return list(self.session.scalars(stmt).all())

    def create(self, **kwargs) -> Seat:
        seat = Seat(**kwargs)
        self.session.add(seat)
        self.session.flush()
        return seat


class PaymentSimulationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_booking_id(self, booking_id: int) -> PaymentSimulation | None:
        return self.session.scalar(select(PaymentSimulation).where(PaymentSimulation.booking_id == booking_id))

    def list_all(self) -> list[PaymentSimulation]:
        stmt = select(PaymentSimulation).order_by(PaymentSimulation.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def create(self, **kwargs) -> PaymentSimulation:
        payment = PaymentSimulation(**kwargs)
        self.session.add(payment)
        self.session.flush()
        return payment


class EmailLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_all(self) -> list[EmailLog]:
        stmt = select(EmailLog).order_by(EmailLog.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def list_for_ticket(self, ticket_id: int) -> list[EmailLog]:
        stmt = select(EmailLog).where(EmailLog.ticket_id == ticket_id).order_by(EmailLog.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def create(self, **kwargs) -> EmailLog:
        email_log = EmailLog(**kwargs)
        self.session.add(email_log)
        self.session.flush()
        return email_log


def _seat_status_count_query(status: str, event_ids: Sequence[int] | None = None):
    stmt = select(Seat.event_id, func.count(Seat.id)).where(Seat.status == status)
    if event_ids:
        stmt = stmt.where(Seat.event_id.in_(event_ids))
    return stmt.group_by(Seat.event_id)


def get_paid_counts_by_event(session: Session, event_ids: Sequence[int] | None = None) -> dict[int, int]:
    return {event_id: int(count) for event_id, count in session.execute(_seat_status_count_query("sold", event_ids)).all()}


def get_available_counts_by_event(session: Session, event_ids: Sequence[int] | None = None) -> dict[int, int]:
    return {
        event_id: int(count)
        for event_id, count in session.execute(_seat_status_count_query("available", event_ids)).all()
    }


def get_reserved_counts_by_event(session: Session, event_ids: Sequence[int] | None = None) -> dict[int, int]:
    return {
        event_id: int(count)
        for event_id, count in session.execute(_seat_status_count_query("reserved_pending_payment", event_ids)).all()
    }


def get_checked_in_counts_by_event(session: Session, event_ids: Sequence[int] | None = None) -> dict[int, int]:
    stmt = select(Ticket.event_id, func.count(Ticket.id)).where(Ticket.status == "used")
    if event_ids:
        stmt = stmt.where(Ticket.event_id.in_(event_ids))
    stmt = stmt.group_by(Ticket.event_id)
    return {event_id: int(count) for event_id, count in session.execute(stmt).all()}


def get_revenue_by_event(session: Session, event_ids: Sequence[int] | None = None) -> dict[int, int]:
    stmt = select(Booking.event_id, func.coalesce(func.sum(Booking.amount_kzt), 0)).where(Booking.status == "paid")
    if event_ids:
        stmt = stmt.where(Booking.event_id.in_(event_ids))
    stmt = stmt.group_by(Booking.event_id)
    return {event_id: int(amount) for event_id, amount in session.execute(stmt).all()}


def list_all_events_with_children(session: Session) -> list[Event]:
    stmt = (
        select(Event)
        .options(
            joinedload(Event.organizer),
            selectinload(Event.bookings).joinedload(Booking.user),
            selectinload(Event.tickets).joinedload(Ticket.user),
            selectinload(Event.seats),
        )
        .order_by(Event.event_datetime.asc())
    )
    return list(session.scalars(stmt).unique().all())
