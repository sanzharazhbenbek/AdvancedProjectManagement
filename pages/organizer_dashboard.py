from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_empty_state, render_kpi_row, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_event_management_table
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.analytics_service import get_organizer_dashboard
from services.auth_service import get_current_user
from utils.formatters import format_kzt, format_percent


def render_page() -> None:
    bootstrap_page("Organizer Dashboard")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access organizer tools.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "organizer":
        flash("warning", "This dashboard is for organizers only.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    dashboard = get_organizer_dashboard(current_user["id"])

    render_page_header(
        "Organizer dashboard",
        "Monitor sales, fill rate, and check-in performance for your events from one clean workspace.",
    )
    render_kpi_row(
        [
            {"label": "Total events", "value": dashboard["metrics"]["total_events"]},
            {"label": "Tickets sold", "value": dashboard["metrics"]["tickets_sold"]},
            {"label": "Revenue", "value": format_kzt(dashboard["metrics"]["revenue_kzt"])},
            {"label": "Checked-in attendees", "value": dashboard["metrics"]["checked_in_attendees"]},
            {"label": "Available seats", "value": dashboard["metrics"]["available_seats"]},
            {"label": "Reserved seats", "value": dashboard["metrics"]["reserved_seats"]},
            {"label": "Fill rate", "value": format_percent(dashboard["metrics"]["fill_rate"])},
        ]
    )

    action_columns = st.columns(3, gap="medium")
    with action_columns[0]:
        if st.button("Create a new event", width="stretch", type="primary"):
            navigate_to(ROUTE_TO_PAGE["create_event"], route="create_event")
    with action_columns[1]:
        if st.button("Manage my events", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["my_events"], route="my_events")
    with action_columns[2]:
        if st.button("Open reports", width="stretch", type="secondary"):
            navigate_to(ROUTE_TO_PAGE["organizer_reports"], route="organizer_reports")

    st.subheader("Event management snapshot")
    if not dashboard["event_rows"]:
        render_empty_state("No events yet", "Create your first event to unlock ticketing, QR check-in, and attendance analytics.")
        return

    render_event_management_table(dashboard["event_rows"])
    top_event = sorted(dashboard["event_rows"], key=lambda event: event["sold_count"], reverse=True)[0]
    st.info(
        f"Top event right now: {top_event['title']} with {top_event['sold_count']} tickets sold and {top_event['checked_in_count']} attendee check-ins."
    )


render_page()
