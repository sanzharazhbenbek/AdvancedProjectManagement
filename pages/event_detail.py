from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_selected_event, navigate_to, remember_redirect, set_selected_booking, set_selected_event
from services.auth_service import get_current_user
from services.booking_service import create_pending_booking
from services.event_service import get_event_detail
from utils.formatters import format_datetime, format_kzt, format_percent


def render_page() -> None:
    bootstrap_page("Event Details")
    current_user = get_current_user()
    render_sidebar(current_user)

    event_id = _read_event_id()
    if event_id is None:
        st.warning("Choose an event from the discover page.")
        if st.button("Back to events", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["discover"], route="discover")
        return

    set_selected_event(event_id)
    event = get_event_detail(event_id, viewer_id=current_user["id"] if current_user else None)
    if event is None:
        st.error("This event could not be found.")
        if st.button("Back to events", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["discover"], route="discover")
        return

    render_page_header(
        event["title"],
        f"{event['organizer_name']} • {format_datetime(event['event_datetime'])} • {event['venue']}, {event['city']}",
        stats=[
            {"label": "Price", "value": format_kzt(event["price_kzt"])},
            {"label": "Capacity", "value": event["capacity"]},
            {"label": "Sold", "value": event["sold_count"]},
            {"label": "Fill rate", "value": format_percent(event["fill_rate"])},
        ],
    )
    render_status_pills(event["category"], event["runtime_status"])

    image_col, detail_col = st.columns([1.2, 1], gap="large")
    with image_col:
        if event.get("image_url"):
            st.image(event["image_url"], width="stretch")
    with detail_col:
        st.markdown("### Event overview")
        st.write(event["description"])
        st.write(f"**Organizer:** {event['organizer_name']}")
        st.write(f"**Date and time:** {format_datetime(event['event_datetime'])}")
        st.write(f"**Venue:** {event['venue']}, {event['city']}")
        st.write(f"**Remaining tickets:** {event['remaining_count']}")

    action_columns = st.columns([1, 1, 1], gap="medium")
    if action_columns[0].button("Back to events", width="stretch"):
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    if event["viewer_has_paid_ticket"] and event["viewer_ticket_id"]:
        if action_columns[1].button("Open my ticket", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=event["viewer_ticket_id"])
        return

    booking_disabled = not event["can_book"]
    if action_columns[1].button("Book ticket", width="stretch", disabled=booking_disabled):
        if current_user is None:
            remember_redirect(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=event_id)
            flash("warning", "Sign in to continue to payment.")
            navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
        booking, errors = create_pending_booking(current_user["id"], event_id)
        for error in errors:
            st.warning(error)
        if booking and booking.get("ticket_id"):
            navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=booking["ticket_id"])
        if booking and booking["status"] == "pending_payment":
            set_selected_booking(booking["booking_id"])
            navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=booking["booking_id"])

    if booking_disabled:
        action_columns[2].info("Booking is available only for upcoming events with open inventory.")


def _read_event_id() -> int | None:
    raw = st.query_params.get("event_id")
    if raw:
        return int(raw)
    return get_selected_event()


render_page()
