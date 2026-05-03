from __future__ import annotations

import streamlit as st

from components.cards import render_ticket_card
from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to, remember_redirect
from services.auth_service import get_current_user
from services.booking_service import get_user_ticket_rows


def render_page() -> None:
    bootstrap_page("My Tickets")
    current_user = get_current_user()
    if current_user is None:
        remember_redirect(ROUTE_TO_PAGE["user_dashboard"], route="user_dashboard")
        flash("warning", "Sign in to access your tickets.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")

    render_sidebar(current_user)
    tickets = get_user_ticket_rows(current_user["id"])
    render_page_header(
        "My tickets",
        f"Track your bookings, keep your ticket codes close, and open QR tickets quickly for entry. Signed in as {current_user['email']}.",
        stats=[
            {"label": "Total tickets", "value": len(tickets)},
            {"label": "Upcoming", "value": len([ticket for ticket in tickets if ticket['event']['runtime_status'] in {'upcoming', 'sold_out'}])},
            {"label": "Used", "value": len([ticket for ticket in tickets if ticket['status'] == 'used'])},
            {"label": "Cancelled", "value": len([ticket for ticket in tickets if ticket['status'] == 'cancelled'])},
        ],
    )

    profile_col, info_col = st.columns([1, 2], gap="large")
    with profile_col:
        st.info(f"{current_user['full_name']}\n\n{current_user['role_label']}")
    with info_col:
        st.write("Your profile is tied directly to the SQLite-backed ticket ledger, so reruns keep your active tickets and event links stable.")

    if not tickets:
        render_empty_state("No tickets yet", "Browse an event, complete the payment, and your QR ticket will show up here.")
        return

    st.subheader("Ticket wallet")
    columns = st.columns(2, gap="large")
    for index, ticket in enumerate(tickets):
        with columns[index % 2]:
            open_ticket, open_event = render_ticket_card(ticket)
            if open_ticket:
                navigate_to(ROUTE_TO_PAGE["ticket"], route="ticket", ticket_id=ticket["id"])
            if open_event:
                navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=ticket["event"]["id"])


render_page()
