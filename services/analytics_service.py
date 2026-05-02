from __future__ import annotations

from collections import Counter
from typing import Any

from db.database import session_scope
from db.repositories import BookingRepository, EventRepository, get_checked_in_counts_by_event, get_paid_counts_by_event, get_revenue_by_event
from services.booking_service import _expire_pending_bookings_in_session
from services.event_service import derive_event_runtime_status, serialize_event


def get_organizer_dashboard(organizer_id: int) -> dict[str, Any]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        events = EventRepository(session).list_by_organizer(organizer_id)
        return _build_dashboard_payload(session, events)


def get_admin_dashboard() -> dict[str, Any]:
    with session_scope() as session:
        _expire_pending_bookings_in_session(session)
        events = EventRepository(session).list_all()
        return _build_dashboard_payload(session, events, include_recent_bookings=True)


def _build_dashboard_payload(session, events, include_recent_bookings: bool = False) -> dict[str, Any]:
    event_ids = [event.id for event in events]
    sold_map = get_paid_counts_by_event(session, event_ids)
    checked_map = get_checked_in_counts_by_event(session, event_ids)
    revenue_map = get_revenue_by_event(session, event_ids)
    bookings = BookingRepository(session).list_for_events(event_ids) if event_ids else []
    rows: list[dict[str, Any]] = []
    category_counter: Counter[str] = Counter()
    total_capacity = 0
    total_sold = 0
    total_checked_in = 0
    total_revenue = 0

    for event in events:
        sold = sold_map.get(event.id, 0)
        checked = checked_map.get(event.id, 0)
        revenue = revenue_map.get(event.id, 0)
        snapshot = serialize_event(event, sold, checked)
        snapshot["revenue_kzt"] = revenue
        rows.append(snapshot)
        category_counter[event.category] += sold
        total_capacity += event.capacity
        total_sold += sold
        total_checked_in += checked
        total_revenue += revenue

    recent_bookings = [
        {
            "id": booking.id,
            "event_title": booking.event.title if booking.event else "Unknown event",
            "user_name": booking.user.full_name if booking.user else "Unknown user",
            "status": booking.status,
            "amount_kzt": booking.amount_kzt,
            "created_at": booking.created_at,
            "payment_reference": booking.payment.payment_reference if booking.payment else None,
        }
        for booking in (BookingRepository(session).list_recent(limit=10) if include_recent_bookings else bookings[:10])
    ]

    revenue_by_event = [
        {"event": row["title"], "revenue_kzt": row["revenue_kzt"]}
        for row in sorted(rows, key=lambda item: item["revenue_kzt"], reverse=True)
    ]
    tickets_by_event = [
        {"event": row["title"], "tickets_sold": row["sold_count"]}
        for row in sorted(rows, key=lambda item: item["sold_count"], reverse=True)
    ]
    attendance_by_event = [
        {
            "event": row["title"],
            "attendance_rate": (row["checked_in_count"] / row["sold_count"]) if row["sold_count"] else 0,
            "remaining_capacity": row["remaining_count"],
        }
        for row in rows
    ]
    popular_categories = [{"category": name, "tickets_sold": count} for name, count in category_counter.most_common()]

    return {
        "metrics": {
            "total_events": len(events),
            "total_bookings": len(bookings),
            "tickets_sold": total_sold,
            "revenue_kzt": total_revenue,
            "checked_in_attendees": total_checked_in,
            "fill_rate": (total_sold / total_capacity) if total_capacity else 0,
        },
        "event_rows": rows,
        "revenue_by_event": revenue_by_event,
        "tickets_by_event": tickets_by_event,
        "attendance_by_event": attendance_by_event,
        "popular_categories": popular_categories,
        "recent_transactions": recent_bookings,
    }
