from __future__ import annotations

from collections import defaultdict
from math import ceil
from typing import Any

from sqlalchemy import delete, func, select, update

from db.models import Event, Seat
from db.repositories import SeatRepository


CATEGORY_ORDER = ["VIP", "Standard", "Economy"]


def price_by_category(base_price: int) -> dict[str, int]:
    def rounded(value: float) -> int:
        return int(round(value / 500) * 500)

    return {
        "VIP": max(rounded(base_price * 1.8), base_price + 5000),
        "Standard": max(rounded(base_price * 1.35), base_price + 2000),
        "Economy": int(base_price),
    }


def build_seed_layout(event: Event) -> list[tuple[str, int, int]]:
    title = event.title.lower()
    if "workshop" in title:
        return [("VIP", 1, 6), ("Standard", 2, 8), ("Economy", 2, 10)]
    if "breakfast" in title or "meetup" in title:
        return [("VIP", 1, 6), ("Standard", 3, 10), ("Economy", 2, 12)]
    return [("VIP", 2, 10), ("Standard", 4, 15), ("Economy", 4, 20)]


def build_dynamic_layout(capacity: int) -> list[tuple[str, int, int]]:
    if capacity <= 45:
        return [("VIP", 1, 6), ("Standard", 2, 8), ("Economy", 2, 10)]
    if capacity <= 70:
        return [("VIP", 1, 8), ("Standard", 3, 10), ("Economy", 2, 12)]
    if capacity <= 110:
        return [("VIP", 2, 8), ("Standard", 3, 12), ("Economy", 3, 14)]

    vip_target = max(10, round(capacity * 0.15))
    standard_target = max(30, round(capacity * 0.35))
    economy_target = max(capacity - vip_target - standard_target, 20)

    vip_rows = max(1, ceil(vip_target / 10))
    standard_rows = max(2, ceil(standard_target / 15))
    economy_rows = max(2, ceil(economy_target / 20))
    return [("VIP", vip_rows, 10), ("Standard", standard_rows, 15), ("Economy", economy_rows, 20)]


def sync_event_seats(
    session,
    event: Event,
    *,
    mode: str = "dynamic",
    target_capacity: int | None = None,
    force_regenerate: bool = False,
) -> list[Seat]:
    seat_repository = SeatRepository(session)
    existing_seats = seat_repository.list_for_event(event.id)
    if existing_seats and not force_regenerate:
        event.capacity = len(existing_seats)
        event.price_kzt = min(seat.price_kzt for seat in existing_seats)
        session.add(event)
        return existing_seats

    if existing_seats and force_regenerate:
        session.execute(delete(Seat).where(Seat.event_id == event.id))
        session.flush()

    layout = build_seed_layout(event) if mode == "seed" else build_dynamic_layout(target_capacity or event.capacity)
    prices = price_by_category(event.price_kzt)
    created_seats: list[Seat] = []
    row_pointer = ord("A")
    for category, row_count, seats_per_row in layout:
        for _ in range(row_count):
            row_label = chr(row_pointer)
            row_pointer += 1
            for seat_number in range(1, seats_per_row + 1):
                created_seats.append(
                    SeatRepository(session).create(
                        event_id=event.id,
                        category=category,
                        row_label=row_label,
                        seat_number=seat_number,
                        price_kzt=prices[category],
                        status="available",
                    )
                )

    event.capacity = len(created_seats)
    event.price_kzt = min(prices.values())
    session.add(event)
    session.flush()
    return created_seats


def build_seat_inventory_payload(seats: list[Seat]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    category_prices: dict[str, int] = {}
    counts = {"available": 0, "reserved_pending_payment": 0, "sold": 0, "blocked": 0}

    for seat in seats:
        category_prices[seat.category] = seat.price_kzt
        counts[seat.status] = counts.get(seat.status, 0) + 1
        grouped[seat.category][seat.row_label].append(serialize_seat(seat))

    categories = []
    for category in CATEGORY_ORDER:
        if category not in grouped:
            continue
        categories.append(
            {
                "category": category,
                "price_kzt": category_prices.get(category, 0),
                "rows": [
                    {"row_label": row_label, "seats": seats_in_row}
                    for row_label, seats_in_row in sorted(grouped[category].items())
                ],
            }
        )

    return {
        "categories": categories,
        "counts": counts,
        "available_count": counts.get("available", 0),
        "reserved_count": counts.get("reserved_pending_payment", 0),
        "sold_count": counts.get("sold", 0),
        "blocked_count": counts.get("blocked", 0),
    }


def serialize_seat(seat: Seat) -> dict[str, Any]:
    return {
        "id": seat.id,
        "event_id": seat.event_id,
        "category": seat.category,
        "row_label": seat.row_label,
        "seat_number": seat.seat_number,
        "price_kzt": seat.price_kzt,
        "status": seat.status,
        "booking_id": seat.booking_id,
    }


def reserve_seat_for_booking(session, seat_id: int, booking_id: int) -> bool:
    result = session.execute(
        update(Seat)
        .where(Seat.id == seat_id, Seat.status == "available", Seat.booking_id.is_(None))
        .values(status="reserved_pending_payment", booking_id=booking_id, updated_at=func.now())
    )
    session.flush()
    return bool(result.rowcount)


def release_seat(session, seat_id: int | None) -> None:
    if seat_id is None:
        return
    session.execute(
        update(Seat)
        .where(Seat.id == seat_id)
        .values(status="available", booking_id=None, updated_at=func.now())
    )
    session.flush()


def mark_seat_sold(session, seat_id: int | None, booking_id: int | None) -> None:
    if seat_id is None:
        return
    session.execute(
        update(Seat)
        .where(Seat.id == seat_id)
        .values(status="sold", booking_id=booking_id, updated_at=func.now())
    )
    session.flush()


def block_seat(session, seat_id: int | None) -> None:
    if seat_id is None:
        return
    session.execute(update(Seat).where(Seat.id == seat_id).values(status="blocked", updated_at=func.now()))
    session.flush()
