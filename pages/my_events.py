from __future__ import annotations

import streamlit as st

from components.forms import render_event_form
from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_attendee_table, render_event_management_table
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.auth_service import get_current_user
from services.event_service import cancel_event, list_event_attendees, list_organizer_events, update_event
from utils.formatters import format_datetime, format_kzt, format_percent


def render_page() -> None:
    bootstrap_page("My Events")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to manage your events.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "organizer":
        flash("warning", "Only organizers can access this page.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    events = list_organizer_events(current_user)
    render_page_header("My events", "Edit event data, review attendee lists, and open the organizer-only QR validation workflow.")

    if not events:
        render_empty_state("No events to manage", "Create your first event to unlock attendee management and reporting.")
        return

    render_event_management_table(events)
    selected_event_id = st.selectbox(
        "Choose an event to manage",
        options=[event["id"] for event in events],
        format_func=lambda value: next(
            f"{event['title']} • {format_datetime(event['event_datetime'])}" for event in events if event["id"] == value
        ),
    )
    selected_event = next(event for event in events if event["id"] == selected_event_id)
    attendee_rows, attendee_error = list_event_attendees(current_user, selected_event_id)

    overview_tab, edit_tab, attendees_tab, checkin_tab = st.tabs(["Overview", "Edit", "Attendees", "Check-in"])
    with overview_tab:
        if selected_event.get("image_url"):
            st.image(selected_event["image_url"], width="stretch")
        st.write(selected_event["description"])
        st.write(f"**Venue:** {selected_event['venue']}, {selected_event['city']}")
        st.write(f"**Price:** {format_kzt(selected_event['price_kzt'])}")
        st.write(f"**Fill rate:** {format_percent(selected_event['fill_rate'])}")
        action_columns = st.columns(2)
        if action_columns[0].button("Open public event page", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=selected_event_id)
        if action_columns[1].button("Cancel event", width="stretch"):
            success, message = cancel_event(current_user, selected_event_id)
            if success:
                flash("warning", message)
                navigate_to(ROUTE_TO_PAGE["my_events"], route="my_events", event_id=selected_event_id)
            st.error(message)

    with edit_tab:
        payload = render_event_form(selected_event, submit_label="Save changes", key_prefix=f"edit_event_{selected_event_id}")
        if payload is not None:
            updated_event, errors = update_event(current_user, selected_event_id, payload)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                flash("success", f"{updated_event['title']} was updated.")
                navigate_to(ROUTE_TO_PAGE["my_events"], route="my_events", event_id=selected_event_id)

    with attendees_tab:
        if attendee_error:
            st.error(attendee_error)
        elif not attendee_rows:
            render_empty_state("No attendees yet", "Paid tickets will appear here together with their check-in status.")
        else:
            render_attendee_table(attendee_rows)

    with checkin_tab:
        st.write("Use the dedicated check-in screen for manual code entry or pasted QR payload validation.")
        if st.button("Open check-in tool", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["check_in"], route="check_in", event_id=selected_event_id)


render_page()
