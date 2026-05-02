from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_attendee_table, render_event_management_table, render_seat_table
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.auth_service import get_current_user
from services.event_service import cancel_event, get_event_seat_inventory, list_all_events_for_admin, list_event_attendees
from utils.formatters import format_datetime, format_kzt, format_percent


def render_page() -> None:
    bootstrap_page("Manage Events")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access event management.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "admin":
        flash("warning", "Only admins can access this page.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    events = list_all_events_for_admin()
    render_page_header("Manage events", "Review platform inventory, inspect attendees, and cancel events when business rules require it.")

    if not events:
        render_empty_state("No events found", "Seeded and organizer-created events will appear here.")
        return

    render_event_management_table(events)
    default_event_id = _read_event_id(events)
    default_index = next((index for index, event in enumerate(events) if event["id"] == default_event_id), 0)
    selected_event_id = st.selectbox(
        "Choose an event",
        options=[event["id"] for event in events],
        index=default_index,
        format_func=lambda value: next(f"{event['title']} • {event['city']}" for event in events if event["id"] == value),
    )
    selected_event = next(event for event in events if event["id"] == selected_event_id)
    attendees, error = list_event_attendees(current_user, selected_event_id)
    seat_inventory, seat_error = get_event_seat_inventory(selected_event_id, actor=current_user)

    overview_tab, attendees_tab, seats_tab, checkin_tab = st.tabs(["Overview", "Attendees", "Seats", "Check-in"])
    with overview_tab:
        if selected_event.get("image_url"):
            st.image(selected_event["image_url"], width="stretch")
        st.write(selected_event["description"])
        st.write(f"**Date:** {format_datetime(selected_event['event_datetime'])}")
        st.write(f"**Venue:** {selected_event['venue']}, {selected_event['city']}")
        st.write(f"**Price:** {format_kzt(selected_event['price_kzt'])}")
        st.write(f"**Fill rate:** {format_percent(selected_event['fill_rate'])}")
        if st.button("Cancel this event", width="stretch", type="secondary"):
            success, message = cancel_event(current_user, selected_event_id)
            if success:
                flash("warning", message)
                navigate_to(ROUTE_TO_PAGE["manage_events"], route="manage_events", event_id=selected_event_id)
            st.error(message)

    with attendees_tab:
        if error:
            st.error(error)
        elif not attendees:
            render_empty_state("No attendees yet", "Paid tickets will appear here with their current check-in status.")
        else:
            render_attendee_table(attendees)

    with seats_tab:
        if seat_error:
            st.error(seat_error)
        elif not seat_inventory or not seat_inventory["categories"]:
            render_empty_state("No seat inventory", "Seats will appear here once the event inventory exists.")
        else:
            st.write(
                f"Available: **{seat_inventory['available_count']}** • Reserved: **{seat_inventory['reserved_count']}** • Sold: **{seat_inventory['sold_count']}**"
            )
            seat_rows = [
                seat
                for category in seat_inventory["categories"]
                for row in category["rows"]
                for seat in row["seats"]
            ]
            render_seat_table(seat_rows)

    with checkin_tab:
        if st.button("Open global check-in tool", width="stretch", type="primary"):
            navigate_to(ROUTE_TO_PAGE["check_in"], route="check_in", event_id=selected_event_id)


def _read_event_id(events: list[dict]) -> int | None:
    raw = st.query_params.get("event_id")
    if raw is None:
        return None
    event_id = int(raw)
    return event_id if any(event["id"] == event_id for event in events) else None


render_page()
