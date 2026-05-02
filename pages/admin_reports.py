from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import bootstrap_page, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_recent_transactions
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.analytics_service import get_admin_dashboard
from services.auth_service import get_current_user
from utils.formatters import format_kzt


def render_page() -> None:
    bootstrap_page("Admin Reports")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access admin reports.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "admin":
        flash("warning", "Only admins can access this page.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    dashboard = get_admin_dashboard()
    render_page_header(
        "Platform reports",
        "Inspect revenue, capacity, attendance, category demand, and recent transactions across the entire EventSphere platform.",
        stats=[
            {"label": "Revenue", "value": format_kzt(dashboard["metrics"]["revenue_kzt"])},
            {"label": "Bookings", "value": dashboard["metrics"]["total_bookings"]},
            {"label": "Tickets sold", "value": dashboard["metrics"]["tickets_sold"]},
            {"label": "Checked in", "value": dashboard["metrics"]["checked_in_attendees"]},
        ],
    )

    revenue_df = pd.DataFrame(dashboard["revenue_by_event"]).set_index("event") if dashboard["revenue_by_event"] else pd.DataFrame()
    tickets_df = pd.DataFrame(dashboard["tickets_by_event"]).set_index("event") if dashboard["tickets_by_event"] else pd.DataFrame()
    category_df = pd.DataFrame(dashboard["popular_categories"]).set_index("category") if dashboard["popular_categories"] else pd.DataFrame()

    first_row, second_row = st.columns(2, gap="large")
    with first_row:
        st.subheader("Revenue by event")
        if revenue_df.empty:
            st.info("No revenue yet.")
        else:
            st.bar_chart(revenue_df)
    with second_row:
        st.subheader("Tickets sold by event")
        if tickets_df.empty:
            st.info("No sales yet.")
        else:
            st.bar_chart(tickets_df)

    st.subheader("Popular categories")
    if category_df.empty:
        st.info("Category trends will appear once tickets are sold.")
    else:
        st.bar_chart(category_df)

    attendance_df = pd.DataFrame(dashboard["attendance_by_event"])
    st.subheader("Attendance rate and remaining capacity")
    if attendance_df.empty:
        st.info("Attendance data is not available yet.")
    else:
        st.dataframe(attendance_df, width="stretch", hide_index=True)

    st.subheader("Recent transactions")
    render_recent_transactions(dashboard["recent_transactions"])


render_page()
