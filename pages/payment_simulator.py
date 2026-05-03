from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_query_param, get_selected_booking, navigate_to, remember_redirect
from services.auth_service import get_current_user
from services.payment_service import cancel_payment, get_payment_context
from services.qr_service import generate_qr_image
from utils.date_utils import format_countdown
from utils.formatters import format_datetime, format_kzt, mask_reference, seat_label


def render_page() -> None:
    bootstrap_page("Payment Status")
    current_user = get_current_user()
    if current_user is None:
        booking_id = _read_booking_id()
        if booking_id is not None:
            remember_redirect(ROUTE_TO_PAGE["payment"], route="payment", booking_id=booking_id)
        flash("warning", "Sign in to continue tracking this booking.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")

    render_sidebar(current_user)

    booking_id = _read_booking_id()
    if booking_id is None:
        st.error("No booking was selected for payment.")
        if st.button("Back to discover", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["discover"], route="discover")
        return

    context, error = get_payment_context(booking_id)
    if error or context is None:
        st.error(error or "Payment context could not be loaded.")
        return

    render_page_header(
        "Payment instructions",
        "Step 1: Keep this page open. Step 2: Scan the QR on another device. Step 3: Confirm the payment on the opened page. Step 4: Return here and refresh your status.",
        stats=[
            {"label": "Booking ID", "value": context["booking_id"]},
            {"label": "Amount", "value": format_kzt(context["amount_kzt"])},
            {"label": "Tickets", "value": context["ticket_count"]},
            {"label": "Deadline", "value": format_countdown(context["payment_deadline"])},
            {"label": "Provider", "value": "Kaspi QR"},
        ],
    )
    render_status_pills(context["event"]["category"], context["booking_status"])

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("### Selected tickets")
        st.write(f"**Event:** {context['event']['title']}")
        st.write(f"**Customer email:** {context['customer_email']}")
        for index, seat in enumerate(context["seats"], start=1):
            st.write(
                f"**Seat {index}:** {seat_label(seat['category'], seat['row_label'], seat['seat_number'])} • {format_kzt(seat['price_kzt'])}"
            )
        st.write(f"**Date:** {format_datetime(context['event']['event_datetime'])}")
        st.write(f"**Payment reference:** {mask_reference(context['payment']['payment_reference'])}")
        st.write(f"**Payment status:** {context['payment']['status'].replace('_', ' ').title()}")

    with right:
        st.markdown("### Scan to confirm payment")
        qr_payload = context["payment"].get("qr_payload") or ""
        if qr_payload:
            st.image(generate_qr_image(qr_payload), width=280)
        st.caption("Use the QR code to open the payment confirmation page on another device.")

    if context["booking_status"] == "paid" and context["ticket_id"]:
        st.success("Payment already confirmed.")
        label = "Open tickets" if context["ticket_count"] > 1 else "Open ticket"
        if st.button(label, width="stretch", type="primary"):
            _open_post_payment_destination(context)
        return

    if context["booking_status"] in {"cancelled", "expired"}:
        st.error(f"This booking is {context['booking_status'].replace('_', ' ')}.")
        if st.button("Back to event", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=context["event"]["id"])
        return

    action_left, action_right = st.columns(2, gap="medium")
    if action_left.button("Refresh payment status", width="stretch", type="primary"):
        st.rerun()

    if action_right.button("Cancel booking", width="stretch", type="secondary"):
        success, message = cancel_payment(booking_id)
        if success:
            flash("info", message)
            navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=context["event"]["id"])
        else:
            st.error(message)


def _open_post_payment_destination(context: dict) -> None:
    if context["ticket_count"] > 1:
        navigate_to(ROUTE_TO_PAGE["user_dashboard"], route="user_dashboard")
        return
    navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=context["ticket_id"])


def _read_booking_id() -> int | None:
    raw = get_query_param("booking_id")
    if raw:
        return int(raw)
    return get_selected_booking()


render_page()
