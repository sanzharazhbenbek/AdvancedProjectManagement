from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_query_param, navigate_to
from services.auth_service import get_current_user
from services.booking_service import check_in_ticket, validate_ticket_for_check_in
from services.event_service import list_all_events_for_admin, list_organizer_events


CHECK_IN_STATE_KEY = "eventsphere_check_in_result"


def render_page() -> None:
    bootstrap_page("Check In")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access ticket validation.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] not in {"organizer", "admin"}:
        flash("warning", "You do not have access to the check-in tool.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    events = list_organizer_events(current_user) if current_user["role"] == "organizer" else list_all_events_for_admin()
    if not events:
        render_empty_state("No manageable events yet", "Create an event first or wait for event assignments to appear.")
        return

    event_options = [(None, "All events")] if current_user["role"] == "admin" else []
    event_options.extend((event["id"], f"{event['title']} • {event['city']}") for event in events)
    default_event_id = _read_event_id()
    selected_index = next((idx for idx, option in enumerate(event_options) if option[0] == default_event_id), 0)
    selected_event_id = st.selectbox(
        "Event scope",
        options=event_options,
        index=selected_index,
        format_func=lambda option: option[1],
    )[0]

    render_page_header(
        "QR ticket check-in",
        "Validate tickets manually or paste a QR payload. Organizers can only validate their own events, while admins can validate across the platform.",
    )

    with st.form("check_in_form"):
        ticket_code = st.text_input("Ticket code", placeholder="ES-XXXXXXX")
        qr_payload_text = st.text_area("QR payload text", placeholder="Optional. Paste the scanned QR text here.", height=120)
        submitted = st.form_submit_button("Validate", width="stretch", type="primary")

    if submitted:
        st.session_state[CHECK_IN_STATE_KEY] = validate_ticket_for_check_in(
            current_user,
            selected_event_id,
            ticket_code=ticket_code,
            qr_payload_text=qr_payload_text,
        )

    result = st.session_state.get(CHECK_IN_STATE_KEY)
    if not result:
        return

    status = result["status"]
    if status == "valid":
        st.success(result["message"])
        st.write(f"**Attendee:** {result['attendee_name']} • {result['attendee_email']}")
        st.write(f"**Event:** {result['event_title']}")
        if result.get("seat_label"):
            st.write(f"**Seat:** {result['seat_label']}")
        if st.button("Check in now", width="stretch", type="primary"):
            success, message = check_in_ticket(current_user, result["ticket_id"])
            if success:
                flash("success", message)
                st.session_state.pop(CHECK_IN_STATE_KEY, None)
                navigate_to(ROUTE_TO_PAGE["check_in"], route="check_in", event_id=selected_event_id)
            else:
                st.error(message)
        return

    if status in {"used", "cancelled", "wrong_event", "unauthorized"}:
        st.warning(result["message"])
    else:
        st.error(result["message"])


def _read_event_id() -> int | None:
    raw = get_query_param("event_id")
    return int(raw) if raw else None


render_page()
