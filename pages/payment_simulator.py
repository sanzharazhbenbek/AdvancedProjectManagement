from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_selected_booking, navigate_to
from services.auth_service import get_current_user
from services.payment_service import cancel_payment, confirm_payment, get_payment_context
from services.qr_service import generate_qr_image
from utils.date_utils import format_countdown
from utils.formatters import format_datetime, format_kzt, mask_reference


def render_page() -> None:
    bootstrap_page("Payment Simulator")
    current_user = get_current_user()
    render_sidebar(current_user)

    booking_id = _read_booking_id()
    if booking_id is None:
        st.error("No booking was selected for payment.")
        if st.button("Back to discover", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["discover"], route="discover")
        return

    context, error = get_payment_context(booking_id)
    if error or context is None:
        st.error(error or "Payment context could not be loaded.")
        return

    render_page_header(
        "Kaspi-style sandbox payment",
        "Sandbox payment simulation. No real money is charged.",
        stats=[
            {"label": "Booking ID", "value": context["booking_id"]},
            {"label": "Amount", "value": format_kzt(context["amount_kzt"])},
            {"label": "Deadline", "value": format_countdown(context["expires_at"])},
            {"label": "Provider", "value": "Kaspi Sandbox"},
        ],
    )
    st.warning("Sandbox payment simulation. No real money is charged.")
    render_status_pills(context["event"]["category"], context["booking_status"])

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("### Payment summary")
        st.write(f"**Event:** {context['event']['title']}")
        st.write(f"**Date:** {format_datetime(context['event']['event_datetime'])}")
        st.write(f"**Reference:** {mask_reference(context['payment']['payment_reference'])}")
        st.write(f"**Status:** {context['payment']['status'].replace('_', ' ').title()}")
        st.write(f"**Created:** {format_datetime(context['created_at'])}")
        st.write(f"**Expires:** {format_datetime(context['expires_at'])}")

    with right:
        st.markdown("### Payment QR")
        st.image(generate_qr_image(context["payment"]["qr_payload"]), width=280)
        st.code(context["payment"]["qr_payload"], language=None)

    if context["booking_status"] == "paid" and context["ticket_id"]:
        st.success("Payment already confirmed.")
        if st.button("Open ticket", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=context["ticket_id"])
        return

    if context["booking_status"] in {"cancelled", "expired"}:
        st.error(f"This booking is {context['booking_status'].replace('_', ' ')}.")
        if st.button("Back to event", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=context["event"]["id"])
        return

    confirm_col, cancel_col = st.columns(2, gap="medium")
    if confirm_col.button("I have paid / Confirm payment", width="stretch"):
        result, errors = confirm_payment(booking_id)
        if errors:
            for error_message in errors:
                st.error(error_message)
        elif result is not None:
            flash("success", "Payment confirmed and ticket issued.")
            navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=result["ticket_id"])

    if cancel_col.button("Cancel booking", width="stretch"):
        success, message = cancel_payment(booking_id)
        if success:
            flash("info", message)
            navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=context["event"]["id"])
        else:
            st.error(message)


def _read_booking_id() -> int | None:
    raw = st.query_params.get("booking_id")
    if raw:
        return int(raw)
    return get_selected_booking()


render_page()
