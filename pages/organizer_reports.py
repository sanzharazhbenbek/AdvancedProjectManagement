from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_event_management_table, render_recent_transactions
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.analytics_service import get_organizer_dashboard
from services.auth_service import get_current_user
from utils.formatters import format_kzt, format_percent


def render_page() -> None:
    bootstrap_page("Organizer Reports")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access organizer reports.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "organizer":
        flash("warning", "Only organizers can access this page.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    dashboard = get_organizer_dashboard(current_user["id"])
    render_page_header(
        "Sales and attendance reports",
        "Track revenue by event, sold inventory, attendance rate, and recent transactions for your portfolio.",
        stats=[
            {"label": "Revenue", "value": format_kzt(dashboard["metrics"]["revenue_kzt"])},
            {"label": "Tickets sold", "value": dashboard["metrics"]["tickets_sold"]},
            {"label": "Bookings", "value": dashboard["metrics"]["total_bookings"]},
            {"label": "Available seats", "value": dashboard["metrics"]["available_seats"]},
            {"label": "Reserved seats", "value": dashboard["metrics"]["reserved_seats"]},
            {"label": "Fill rate", "value": format_percent(dashboard["metrics"]["fill_rate"])},
        ],
    )

    revenue_df = pd.DataFrame(dashboard["revenue_by_event"]).set_index("event") if dashboard["revenue_by_event"] else pd.DataFrame()
    tickets_df = pd.DataFrame(dashboard["tickets_by_event"]).set_index("event") if dashboard["tickets_by_event"] else pd.DataFrame()
    category_df = pd.DataFrame(dashboard["popular_categories"]).set_index("category") if dashboard["popular_categories"] else pd.DataFrame()

    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        st.subheader("Revenue by event")
        if revenue_df.empty:
            st.info("No revenue yet.")
        else:
            st.bar_chart(revenue_df)
    with chart_right:
        st.subheader("Tickets sold by event")
        if tickets_df.empty:
            st.info("No ticket sales yet.")
        else:
            st.bar_chart(tickets_df)

    st.subheader("Popular categories")
    if category_df.empty:
        st.info("Category trends will appear once tickets are sold.")
    else:
        st.bar_chart(category_df)

    attendance_df = pd.DataFrame(dashboard["attendance_by_event"])
    st.subheader("Attendance and remaining capacity")
    if attendance_df.empty:
        st.info("Attendance data is not available yet.")
    else:
        st.dataframe(attendance_df, width="stretch", hide_index=True)

    st.subheader("Event seat and sales snapshot")
    if not dashboard["event_rows"]:
        render_empty_state("No managed events yet", "Create an event to start tracking seats, bookings, and attendance.")
    else:
        render_event_management_table(dashboard["event_rows"])

    st.subheader("Recent transactions")
    render_recent_transactions(dashboard["recent_transactions"])


render_page()
