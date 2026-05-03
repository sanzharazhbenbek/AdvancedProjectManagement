from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import (
    flash,
    get_query_param,
    get_selected_event,
    navigate_to,
    remember_redirect,
    set_selected_booking,
    set_selected_event,
)
from services.auth_service import get_current_user
from services.booking_service import create_pending_bookings
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

    _render_purchase_context(event)

    action_columns = st.columns([1, 1, 1], gap="medium")
    if action_columns[0].button("Back to events", width="stretch", type="secondary"):
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    secondary_label = None
    secondary_route: dict[str, int] | None = None
    if event.get("viewer_pending_booking_id"):
        secondary_label = "Continue pending payment"
        secondary_route = {"booking_id": event["viewer_pending_booking_id"]}
    elif event["viewer_has_paid_ticket"] and event["viewer_ticket_id"]:
        secondary_label = "Open latest ticket"
        secondary_route = {"ticket_id": event["viewer_ticket_id"]}

    if secondary_label and secondary_route:
        if action_columns[1].button(secondary_label, width="stretch", type="secondary"):
            if "booking_id" in secondary_route:
                set_selected_booking(secondary_route["booking_id"])
                navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=secondary_route["booking_id"])
            else:
                navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=secondary_route["ticket_id"])

    booking_disabled = not event["can_book"]
    if action_columns[2].button(
        "Book tickets",
        width="stretch",
        disabled=booking_disabled,
        type="primary",
    ):
        if current_user is None:
            remember_redirect(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=event_id)
            flash("warning", "Sign in to choose seats and continue to payment.")
            navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
        st.session_state[f"eventsphere_booking_panel_{event_id}"] = True

    if booking_disabled:
        st.info("Booking is available only for upcoming events with open inventory.")
        return
    if current_user is None:
        return

    show_booking_panel = st.session_state.get(f"eventsphere_booking_panel_{event_id}", False) or bool(
        event.get("viewer_pending_booking_id")
    )
    if not show_booking_panel:
        return

    _render_booking_panel(event, current_user)


def _render_purchase_context(event: dict) -> None:
    if event.get("viewer_pending_booking_id"):
        pending_count = event.get("viewer_pending_ticket_count", 0)
        pending_total = event.get("viewer_pending_total_amount_kzt", 0)
        st.info(
            f"You have {pending_count} seat{'s' if pending_count != 1 else ''} waiting for payment"
            f" ({format_kzt(pending_total)}). You can continue that payment or start a new seat selection below."
        )


def _render_booking_panel(event: dict, current_user: dict) -> None:
    inventory, error = get_event_seat_inventory(event["id"])
    if error or inventory is None:
        st.error(error or "Seat inventory could not be loaded.")
        return

    st.markdown("### Step 1: Select your seats")
    st.caption(
        "Step 1: Choose category and quantity • Step 2: Select seats • Step 3: Scan payment QR • Step 4: Confirm payment • Step 5: Receive tickets"
    )
    _render_seat_legend()

    category_options = [item["category"] for item in inventory["categories"]]
    if not category_options:
        st.warning("No seats are configured for this event yet.")
        return

    selected_category = st.selectbox("Seat category", options=category_options, key=f"seat-category-{event['id']}")
    category_payload = next(item for item in inventory["categories"] if item["category"] == selected_category)
    available_in_category = sum(
        1
        for row in category_payload["rows"]
        for seat in row["seats"]
        if seat["status"] == "available"
    )
    if available_in_category <= 0:
        st.warning("This category is sold out. Choose a different category.")
        return

    quantity_options = list(range(1, min(available_in_category, 6) + 1))
    quantity = st.selectbox("How many tickets?", options=quantity_options, key=f"seat-quantity-{event['id']}")

    selected_ids_key = f"eventsphere_selected_seats_{event['id']}"
    notice_key = f"eventsphere_selection_notice_{event['id']}"
    seat_lookup = {
        seat["id"]: seat
        for row in category_payload["rows"]
        for seat in row["seats"]
    }
    selected_ids = _sanitize_selected_seats(
        event["id"],
        seat_lookup,
        quantity=quantity,
        selected_ids_key=selected_ids_key,
    )

    info_left, info_right, info_third = st.columns(3, gap="medium")
    info_left.metric("Category price", format_kzt(category_payload["price_kzt"]))
    info_right.metric("Available in category", available_in_category)
    info_third.metric("Selected", f"{len(selected_ids)} / {quantity}")

    _render_seat_rows(
        event["id"],
        category_payload,
        selected_ids_key=selected_ids_key,
        selected_ids=selected_ids,
        quantity=quantity,
        notice_key=notice_key,
    )
    selected_ids = _sanitize_selected_seats(
        event["id"],
        seat_lookup,
        quantity=quantity,
        selected_ids_key=selected_ids_key,
    )

    notice = st.session_state.get(notice_key)
    if notice:
        st.warning(notice)

    selected_seats = [seat_lookup[seat_id] for seat_id in selected_ids if seat_id in seat_lookup]
    selected_seats.sort(key=lambda seat: (seat["row_label"], seat["seat_number"]))
    if not selected_seats:
        st.info("Choose seats from the map below to continue.")
        return

    _render_selected_seat_summary(event, selected_seats, quantity)
    can_continue = len(selected_seats) == quantity
    if not can_continue:
        st.caption("Select the full quantity to continue to payment.")

    if st.button(
        f"Reserve {quantity} ticket{'s' if quantity != 1 else ''} and continue to payment",
        width="stretch",
        type="primary",
        disabled=not can_continue,
    ):
        booking, errors = create_pending_bookings(current_user["id"], event["id"], [seat["id"] for seat in selected_seats])
        for error_message in errors:
            st.warning(error_message)
        if booking and booking["status"] == "pending_payment":
            st.session_state[selected_ids_key] = []
            st.session_state[notice_key] = None
            flash(
                "success",
                f"{booking['ticket_count']} seat{'s' if booking['ticket_count'] != 1 else ''} reserved. Continue with payment on the next screen.",
            )
            set_selected_booking(booking["booking_id"])
            navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=booking["booking_id"])


def _render_seat_rows(
    event_id: int,
    category_payload: dict,
    *,
    selected_ids_key: str,
    selected_ids: list[int],
    quantity: int,
    notice_key: str,
) -> None:
    st.markdown("### Seat map")
    for row_payload in category_payload["rows"]:
        st.write(f"**Row {row_payload['row_label']}**")
        seats = row_payload["seats"]
        chunk_size = 5
        for start_index in range(0, len(seats), chunk_size):
            seat_chunk = seats[start_index : start_index + chunk_size]
            columns = st.columns(len(seat_chunk), gap="small")
            for column, seat in zip(columns, seat_chunk):
                status = seat["status"]
                is_selected = seat["id"] in selected_ids
                button_type = "primary" if is_selected else "secondary"
                button_disabled = status != "available" and not is_selected
                with column:
                    if st.button(
                        f"{seat['row_label']}-{seat['seat_number']}",
                        key=f"seat-button-{event_id}-{seat['id']}",
                        width="stretch",
                        type=button_type,
                        disabled=button_disabled,
                    ):
                        updated_ids, notice = _toggle_seat_selection(selected_ids, seat["id"], quantity)
                        st.session_state[selected_ids_key] = updated_ids
                        st.session_state[notice_key] = notice
                        st.rerun()
                    status_label = "Selected" if is_selected else status.replace("_", " ").title()
                    st.caption(status_label)


def _toggle_seat_selection(selected_ids: list[int], seat_id: int, quantity: int) -> tuple[list[int], str | None]:
    current_ids = list(selected_ids)
    if seat_id in current_ids:
        current_ids.remove(seat_id)
        return current_ids, None
    if len(current_ids) >= quantity:
        return current_ids, "You already selected the maximum number of tickets for this purchase. Unselect one seat to choose a different seat."
    current_ids.append(seat_id)
    current_ids.sort()
    return current_ids, None


def _sanitize_selected_seats(
    event_id: int,
    seat_lookup: dict[int, dict],
    *,
    quantity: int,
    selected_ids_key: str,
) -> list[int]:
    selected_ids = [
        seat_id
        for seat_id in st.session_state.get(selected_ids_key, [])
        if seat_id in seat_lookup and seat_lookup[seat_id]["status"] == "available"
    ]
    if len(selected_ids) > quantity:
        selected_ids = selected_ids[:quantity]
    st.session_state[selected_ids_key] = selected_ids
    st.session_state.setdefault(f"eventsphere_booking_panel_{event_id}", True)
    return selected_ids


def _render_selected_seat_summary(event: dict, selected_seats: list[dict], quantity: int) -> None:
    total_amount = sum(seat["price_kzt"] for seat in selected_seats)
    st.markdown("### Selected ticket summary")
    st.write(f"**Event:** {event['title']}")
    st.write(f"**Quantity:** {len(selected_seats)} / {quantity}")
    st.write(f"**Category:** {selected_seats[0]['category']}")
    for index, seat in enumerate(selected_seats, start=1):
        st.write(
            f"**Seat {index}:** {seat_label(seat['category'], seat['row_label'], seat['seat_number'])} • {format_kzt(seat['price_kzt'])}"
        )
    st.write(f"**Total price:** {format_kzt(total_amount)}")


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
    raw = get_query_param("event_id")
    if raw:
        return int(raw)
    return get_selected_event()


render_page()
