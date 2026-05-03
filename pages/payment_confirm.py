from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_query_param, navigate_to
from services.auth_service import get_current_user
from services.payment_service import cancel_payment_with_token, confirm_payment_with_token, get_payment_confirmation_context
from utils.date_utils import format_countdown
from utils.formatters import format_datetime, format_kzt, seat_label


def render_page() -> None:
    bootstrap_page("Confirm Payment", sidebar_state="collapsed")
    current_user = get_current_user()
    if current_user is not None:
        render_sidebar(current_user)

    token = str(get_query_param("token", "") or "").strip()
    if not token:
        st.error("Payment token not found.")
        return

    context, error = get_payment_confirmation_context(token)
    if error or context is None:
        st.error(error or "Invalid payment token.")
        return

    render_page_header(
        "Confirm payment",
        "Review the booking details and finish the payment confirmation on this page.",
        stats=[
            {"label": "Event", "value": context["event"]["title"]},
            {"label": "Amount", "value": format_kzt(context["amount_kzt"])},
            {"label": "Tickets", "value": context["ticket_count"]},
            {"label": "Status", "value": context["payment"]["status"].replace("_", " ").title()},
            {"label": "Deadline", "value": format_countdown(context["payment_deadline"])},
        ],
    )
    render_status_pills(status=context["booking_status"])

    st.write(f"**Event:** {context['event']['title']}")
    st.write(f"**Date and time:** {format_datetime(context['event']['event_datetime'])}")
    st.write(f"**Venue:** {context['event']['venue']}, {context['event']['city']}")
    st.write(f"**Customer email:** {context['customer_email']}")
    for index, seat in enumerate(context["seats"], start=1):
        st.write(
            f"**Seat {index}:** {seat_label(seat['category'], seat['row_label'], seat['seat_number'])} • {format_kzt(seat['price_kzt'])}"
        )
    st.write(f"**Amount:** {format_kzt(context['amount_kzt'])}")

    if context["booking_status"] == "paid" and context["ticket_id"]:
        st.success("This payment has already been confirmed.")
        label = "Open tickets" if context["ticket_count"] > 1 else "Open ticket"
        if st.button(label, width="stretch", type="primary"):
            _open_post_payment_destination(context)
        return

    if context["booking_status"] in {"cancelled", "expired"}:
        st.error(f"This booking is {context['booking_status'].replace('_', ' ')}.")
        if st.button("Open booking status", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=context["booking_id"])
        return

    left, right = st.columns(2, gap="medium")
    if left.button("Confirm payment", width="stretch", type="primary"):
        result, errors = confirm_payment_with_token(token)
        if errors:
            for error_message in errors:
                st.error(error_message)
        elif result is not None:
            flash(
                "success",
                f"Payment confirmed and {result['ticket_count']} ticket"
                f"{'' if result['ticket_count'] == 1 else 's'} issued.",
            )
            _open_post_payment_destination(result)

    if right.button("Cancel payment", width="stretch", type="secondary"):
        success, message = cancel_payment_with_token(token)
        if success:
            flash("info", message)
            navigate_to(ROUTE_TO_PAGE["payment"], route="payment", booking_id=context["booking_id"])
        else:
            st.error(message)


def _open_post_payment_destination(context: dict) -> None:
    if context["ticket_count"] > 1:
        navigate_to(ROUTE_TO_PAGE["user_dashboard"], route="user_dashboard")
        return
    navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=context["ticket_id"])


render_page()
