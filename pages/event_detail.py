from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_selected_event, navigate_to, remember_redirect, set_selected_booking, set_selected_event
from services.auth_service import get_current_user
from services.booking_service import create_pending_booking
from services.event_service import get_event_detail, get_event_seat_inventory
from utils.formatters import format_datetime, format_kzt, format_percent, seat_label


def render_page() -> None:
    bootstrap_page("Event Details")
    current_user = get_current_user()
    render_sidebar(current_user)

    event_id = _read_event_id()
    if event_id is None:
        st.warning("Choose an event from the discover page.")
        if st.button("Back to events", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["discover"], route="discover")
        return

    set_selected_event(event_id)
    event = get_event_detail(event_id, viewer_id=current_user["id"] if current_user else None)
    if event is None:
        st.error("This event could not be found.")
        if st.button("Back to events", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["discover"], route="discover")
        return

    render_page_header(
        event["title"],
        f"{event['organizer_name']} • {format_datetime(event['event_datetime'])} • {event['venue']}, {event['city']}",
        stats=[
            {"label": "From price", "value": format_kzt(event["price_from_kzt"])},
            {"label": "Capacity", "value": event["capacity"]},
            {"label": "Available", "value": event["remaining_count"]},
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
        st.write(f"**Sold seats:** {event['sold_count']}")
        st.write(f"**Reserved pending payment:** {event['reserved_count']}")
        st.write(f"**Remaining tickets:** {event['remaining_count']}")

    action_columns = st.columns([1, 1, 1], gap="medium")
    if action_columns[0].button("Back to events", width="stretch", type="secondary"):
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    if event["viewer_has_paid_ticket"] and event["viewer_ticket_id"]:
        if action_columns[1].button("Open my ticket", width="stretch", type="primary"):
            navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=event["viewer_ticket_id"])
        return

    if event.get("viewer_pending_booking_id"):
        pending_seat = event.get("viewer_pending_seat")
        seat_text = (
            seat_label(pending_seat["category"], pending_seat["row_label"], pending_seat["seat_number"])
            if pending_seat
            else "Seat pending"
        )
        st.info(f"You already have a pending booking for {seat_text}. Continue to payment or choose a different seat below.")
        if action_columns[1].button("Continue to payment", width="stretch", type="primary"):
            set_selected_booking(event["viewer_pending_booking_id"])
            navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=event["viewer_pending_booking_id"])
    else:
        booking_disabled = not event["can_book"]
        if action_columns[1].button("Book ticket", width="stretch", disabled=booking_disabled, type="primary"):
            if current_user is None:
                remember_redirect(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=event_id)
                flash("warning", "Sign in to choose a seat and continue to payment.")
                navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
            st.session_state[f"eventsphere_booking_panel_{event_id}"] = True

        if booking_disabled:
            action_columns[2].info("Booking is available only for upcoming events with open inventory.")

    if current_user is None or not event["can_book"]:
        return

    show_booking_panel = st.session_state.get(f"eventsphere_booking_panel_{event_id}", False) or bool(event.get("viewer_pending_booking_id"))
    if not show_booking_panel:
        return

    _render_booking_panel(event, current_user)


def _render_booking_panel(event: dict, current_user: dict) -> None:
    inventory, error = get_event_seat_inventory(event["id"])
    if error or inventory is None:
        st.error(error or "Seat inventory could not be loaded.")
        return

    st.markdown("### Step 1: Select your seat")
    st.caption("Step 1: Select seat • Step 2: Scan payment QR • Step 3: Confirm sandbox payment on the opened page • Step 4: Receive ticket")
    _render_seat_legend()

    category_options = [item["category"] for item in inventory["categories"]]
    if not category_options:
        st.warning("No seats are configured for this event yet.")
        return

    selected_category = st.selectbox("Seat category", options=category_options, key=f"seat-category-{event['id']}")
    category_payload = next(item for item in inventory["categories"] if item["category"] == selected_category)
    row_options = [row["row_label"] for row in category_payload["rows"]]
    selected_row = st.selectbox("Row", options=row_options, key=f"seat-row-{event['id']}")
    row_payload = next(row for row in category_payload["rows"] if row["row_label"] == selected_row)

    selected_seat_id = st.session_state.get(f"eventsphere_selected_seat_{event['id']}")
    _render_seat_grid(event["id"], category_payload["rows"], selected_seat_id)

    available_seats = [seat for seat in row_payload["seats"] if seat["status"] == "available"]
    if not available_seats:
        st.warning("There are no available seats left in this row. Choose a different row.")
        return

    selected_seat_id = st.selectbox(
        "Seat number",
        options=[seat["id"] for seat in available_seats],
        format_func=lambda value: next(
            f"Seat {seat['seat_number']} • {format_kzt(seat['price_kzt'])}" for seat in available_seats if seat["id"] == value
        ),
        key=f"seat-number-{event['id']}",
    )
    st.session_state[f"eventsphere_selected_seat_{event['id']}"] = selected_seat_id
    selected_seat = next(seat for seat in available_seats if seat["id"] == selected_seat_id)

    st.markdown("### Selected seat summary")
    st.write(f"**Event:** {event['title']}")
    st.write(f"**Category:** {selected_seat['category']}")
    st.write(f"**Row:** {selected_seat['row_label']}")
    st.write(f"**Seat number:** {selected_seat['seat_number']}")
    st.write(f"**Final price:** {format_kzt(selected_seat['price_kzt'])}")

    if st.button("Reserve selected seat and continue to payment", width="stretch", type="primary"):
        booking, errors = create_pending_booking(current_user["id"], event["id"], selected_seat["id"])
        for error_message in errors:
            st.warning(error_message)
        if booking and booking.get("ticket_id"):
            navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=booking["ticket_id"])
        if booking and booking["status"] == "pending_payment":
            flash("success", "Seat reserved. Continue with the sandbox payment on the next screen.")
            set_selected_booking(booking["booking_id"])
            navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=booking["booking_id"])


def _render_seat_grid(event_id: int, rows: list[dict], selected_seat_id: int | None) -> None:
    st.markdown("### Seat map")
    for row in rows:
        seat_labels = []
        for seat in row["seats"]:
            status = seat["status"]
            if selected_seat_id == seat["id"]:
                status = "selected"
            seat_labels.append(
                f"<span class='pill pill-{status}' style='margin-right:0.25rem;'>"
                f"{row['row_label']}-{seat['seat_number']}</span>"
            )
        st.markdown(f"**Row {row['row_label']}**<br>{''.join(seat_labels)}", unsafe_allow_html=True)


def _render_seat_legend() -> None:
    st.markdown(
        """
        <span class="pill pill-available">Available</span>
        <span class="pill pill-selected">Selected</span>
        <span class="pill pill-sold">Sold</span>
        <span class="pill pill-reserved_pending_payment">Reserved</span>
        """,
        unsafe_allow_html=True,
    )


def _read_event_id() -> int | None:
    raw = st.query_params.get("event_id")
    if raw:
        return int(raw)
    return get_selected_event()


render_page()
