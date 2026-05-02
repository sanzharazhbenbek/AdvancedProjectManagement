from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import bootstrap_page, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_recent_transactions, render_table, rows_to_csv_bytes
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.analytics_service import get_admin_dashboard
from services.auth_service import get_current_user
from services.event_service import list_admin_operational_rows
from utils.formatters import format_datetime, format_kzt, seat_label


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
    operational_rows = list_admin_operational_rows()
    render_page_header(
        "Platform reports",
        "Inspect revenue, capacity, attendance, and the operational records behind seats, payments, tickets, and delivery.",
        stats=[
            {"label": "Revenue", "value": format_kzt(dashboard["metrics"]["revenue_kzt"])},
            {"label": "Bookings", "value": dashboard["metrics"]["total_bookings"]},
            {"label": "Tickets sold", "value": dashboard["metrics"]["tickets_sold"]},
            {"label": "Checked in", "value": dashboard["metrics"]["checked_in_attendees"]},
        ],
    )

    analytics_tab, bookings_tab, payments_tab, tickets_tab, email_tab = st.tabs(
        ["Analytics", "Bookings", "Payments", "Tickets", "Email logs"]
    )

    with analytics_tab:
        _render_analytics(dashboard)

    with bookings_tab:
        _render_admin_table_tab("Bookings", operational_rows["bookings"], _format_booking_rows)

    with payments_tab:
        _render_admin_table_tab("Payments", operational_rows["payments"], _format_payment_rows)

    with tickets_tab:
        _render_admin_table_tab("Tickets", operational_rows["tickets"], _format_ticket_rows)

    with email_tab:
        _render_admin_table_tab("Email logs", operational_rows["email_logs"], _format_email_rows)


def _render_analytics(dashboard: dict) -> None:
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


def _render_admin_table_tab(title: str, rows: list[dict], formatter) -> None:
    st.subheader(title)
    if not rows:
        st.info(f"No {title.lower()} found.")
        return

    event_options = ["All", *sorted({str(row.get("event_title") or "-") for row in rows})]
    user_options = ["All", *sorted({str(row.get("user_email") or row.get("recipient_email") or "-") for row in rows})]
    status_options = ["All", *sorted({str(row.get("status") or row.get("payment_status") or "-") for row in rows})]
    filters = st.columns(3, gap="medium")
    selected_event = filters[0].selectbox(f"{title} event filter", options=event_options, key=f"{title}-event-filter")
    selected_user = filters[1].selectbox(f"{title} user filter", options=user_options, key=f"{title}-user-filter")
    selected_status = filters[2].selectbox(f"{title} status filter", options=status_options, key=f"{title}-status-filter")

    filtered_rows = [
        row
        for row in rows
        if (selected_event == "All" or str(row.get("event_title") or "-") == selected_event)
        and (selected_user == "All" or str(row.get("user_email") or row.get("recipient_email") or "-") == selected_user)
        and (selected_status == "All" or str(row.get("status") or row.get("payment_status") or "-") == selected_status)
    ]
    formatted_rows = formatter(filtered_rows)
    render_table(formatted_rows)
    st.download_button(
        f"Export {title.lower()} CSV",
        data=rows_to_csv_bytes(filtered_rows),
        file_name=f"eventsphere-{title.lower().replace(' ', '-')}.csv",
        mime="text/csv",
        width="stretch",
        type="primary",
    )


def _format_booking_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "Booking": row["id"],
            "Event": row["event_title"],
            "User": row["user_email"],
            "Status": row["status"],
            "Payment": row.get("payment_status") or "-",
            "Seat": seat_label(row.get("seat_category"), row.get("row_label"), row.get("seat_number")),
            "Amount": format_kzt(row["amount_kzt"]),
            "Created": format_datetime(row["created_at"]),
            "Deadline": format_datetime(row.get("payment_deadline")),
        }
        for row in rows
    ]


def _format_payment_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "Payment": row["payment_id"],
            "Booking": row["booking_id"],
            "Event": row["event_title"],
            "User": row["user_email"],
            "Status": row["status"],
            "Amount": format_kzt(row["amount_kzt"] or 0),
            "Reference": row["payment_reference"],
            "Created": format_datetime(row["created_at"]),
            "Confirmed": format_datetime(row["confirmed_at"]),
        }
        for row in rows
    ]


def _format_ticket_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "Ticket": row["ticket_code"],
            "Event": row["event_title"],
            "User": row["user_email"],
            "Status": row["status"],
            "Seat": seat_label(row.get("category"), row.get("row_label"), row.get("seat_number")),
            "Price": format_kzt(row["price_kzt"] or 0),
            "Created": format_datetime(row["created_at"]),
            "Checked in": format_datetime(row["checked_in_at"]),
        }
        for row in rows
    ]


def _format_email_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "Email log": row["email_log_id"],
            "Event": row.get("event_title") or "-",
            "Recipient": row["recipient_email"],
            "Status": row["status"],
            "Subject": row["subject"],
            "Attachment": row.get("attachment_path") or "-",
            "Created": format_datetime(row["created_at"]),
        }
        for row in rows
    ]


render_page()
