from __future__ import annotations

from pathlib import Path

import streamlit as st

from components.layout import bootstrap_page, render_page_header, render_status_pills
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, get_query_param, get_selected_ticket, navigate_to, remember_redirect
from services.auth_service import get_current_user
from services.booking_service import get_ticket_detail
from services.qr_service import generate_qr_image
from utils.formatters import format_datetime, format_kzt, seat_label


def render_page() -> None:
    bootstrap_page("Ticket View")
    current_user = get_current_user()
    if current_user is None:
        ticket_id = _read_ticket_id()
        if ticket_id is not None:
            remember_redirect(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=ticket_id)
        flash("warning", "Sign in to view your ticket.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")

    render_sidebar(current_user)
    ticket_id = _read_ticket_id()
    if ticket_id is None:
        st.error("No ticket was selected.")
        return

    detail, error = get_ticket_detail(ticket_id, actor=current_user)
    if error or detail is None:
        st.error(error or "Ticket could not be loaded.")
        return

    render_page_header(
        "Digital ticket",
        f"{detail['event']['title']} • {format_datetime(detail['event']['event_datetime'])} • {detail['event']['venue']}, {detail['event']['city']}",
        stats=[
            {"label": "Ticket code", "value": detail["ticket_code"]},
            {"label": "Status", "value": detail["status"].title()},
            {"label": "Seat", "value": seat_label(detail['seat']['category'], detail['seat']['row_label'], detail['seat']['seat_number'])},
            {"label": "Price", "value": format_kzt(detail['seat']['price_kzt'] or 0)},
        ],
    )
    render_status_pills(detail["event"]["category"], detail["status"])

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.image(generate_qr_image(detail["qr_payload"]), width=280)
        attachment_path = detail.get("ticket_file_path")
        if attachment_path and Path(attachment_path).exists():
            file_path = Path(attachment_path)
            mime = "application/pdf" if file_path.suffix.lower() == ".pdf" else "text/html"
            button_label = "Download PDF ticket" if mime == "application/pdf" else "Download ticket file"
            st.download_button(
                button_label,
                data=file_path.read_bytes(),
                file_name=file_path.name,
                mime=mime,
                width="stretch",
                type="primary",
            )
    with right:
        st.write(f"**Attendee:** {detail['user_name']}")
        st.write(f"**Email:** {detail['user_email']}")
        st.write(f"**Seat:** {seat_label(detail['seat']['category'], detail['seat']['row_label'], detail['seat']['seat_number'])}")
        st.write(f"**Venue:** {detail['event']['venue']}, {detail['event']['city']}")
        st.write(f"**Ticket code:**")
        st.code(detail["ticket_code"], language=None)
        st.write(f"**Checked in at:** {format_datetime(detail['checked_in_at'])}")
        if st.button("Back to event", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=detail["event"]["id"])

    st.markdown("### Confirmation details")
    if not detail["email_logs"]:
        st.info("No delivery record was found for this ticket.")
    else:
        for email_log in detail["email_logs"]:
            status_label = _format_delivery_status(email_log["status"])
            st.write(
                f"**{status_label}** • {email_log['recipient_email']} • {format_datetime(email_log['created_at'])}"
            )
            st.caption(email_log["subject"])


def _read_ticket_id() -> int | None:
    raw = get_query_param("ticket_id")
    if raw:
        return int(raw)
    return get_selected_ticket()


def _format_delivery_status(status: str) -> str:
    if status in {"simulated", "delivered"}:
        return "Delivered"
    return status.replace("_", " ").title()


render_page()
