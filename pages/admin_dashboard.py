from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_kpi_row, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_recent_transactions
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.analytics_service import get_admin_dashboard
from services.auth_service import get_current_user
from services.event_service import list_all_user_rows
from utils.formatters import format_kzt


def render_page() -> None:
    bootstrap_page("Admin Dashboard")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access admin tools.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "admin":
        flash("warning", "Only admins can access this page.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    dashboard = get_admin_dashboard()
    users = list_all_user_rows()
    organizers = [user for user in users if user["role"] == "organizer"]

    render_page_header(
        "Admin control center",
        "Monitor platform health, manage people and events, and keep the ticketing lifecycle under control across the entire workspace.",
    )
    render_kpi_row(
        [
            {"label": "Total users", "value": len(users)},
            {"label": "Organizers", "value": len(organizers)},
            {"label": "Events", "value": dashboard["metrics"]["total_events"]},
            {"label": "Bookings", "value": dashboard["metrics"]["total_bookings"]},
            {"label": "Revenue", "value": format_kzt(dashboard["metrics"]["revenue_kzt"])},
        ]
    )

    action_columns = st.columns(3, gap="medium")
    with action_columns[0]:
        if st.button("Manage users", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["manage_users"], route="manage_users")
    with action_columns[1]:
        if st.button("Manage events", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["manage_events"], route="manage_events")
    with action_columns[2]:
        if st.button("Open reports", width="stretch"):
            navigate_to(ROUTE_TO_PAGE["admin_reports"], route="admin_reports")

    st.subheader("Recent bookings")
    render_recent_transactions(dashboard["recent_transactions"])


render_page()
