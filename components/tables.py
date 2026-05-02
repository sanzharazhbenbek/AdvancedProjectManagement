from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from utils.formatters import format_datetime, format_kzt, format_percent, seat_label


def render_table(rows: list[dict[str, Any]], column_order: list[str] | None = None, hide_index: bool = True) -> None:
    if not rows:
        st.info("Nothing to show yet.")
        return
    dataframe = pd.DataFrame(rows)
    if column_order:
        present_columns = [column for column in column_order if column in dataframe.columns]
        dataframe = dataframe[present_columns]
    st.dataframe(dataframe, width="stretch", hide_index=hide_index)


def render_event_management_table(events: list[dict[str, Any]]) -> None:
    rows = [
        {
            "ID": event["id"],
            "Title": event["title"],
            "Date": format_datetime(event["event_datetime"]),
            "City": event["city"],
            "Status": event["runtime_status"],
            "Sold": event["sold_count"],
            "Remaining": event["remaining_count"],
            "Fill rate": format_percent(event["fill_rate"]),
        }
        for event in events
    ]
    render_table(rows)


def render_attendee_table(rows: list[dict[str, Any]]) -> None:
    formatted = [
        {
            "Ticket": row["ticket_code"],
            "Attendee": row["attendee_name"],
            "Email": row["attendee_email"],
            "Seat": seat_label(row.get("seat_category"), row.get("row_label"), row.get("seat_number")),
            "Payment": row.get("payment_status") or "-",
            "Status": row["status"],
            "Checked in at": format_datetime(row["checked_in_at"]),
        }
        for row in rows
    ]
    render_table(formatted)


def render_recent_transactions(rows: list[dict[str, Any]]) -> None:
    formatted = [
        {
            "Booking": row["id"],
            "Event": row["event_title"],
            "Attendee": row.get("user_name", row.get("user_email", "Unknown attendee")),
            "Seat": seat_label(row.get("seat_category"), row.get("row_label"), row.get("seat_number")),
            "Status": row["status"],
            "Amount": format_kzt(row["amount_kzt"]),
            "Created": format_datetime(row["created_at"]),
            "Reference": row.get("payment_reference") or "-",
        }
        for row in rows
    ]
    render_table(formatted)


def render_seat_table(rows: list[dict[str, Any]]) -> None:
    formatted = [
        {
            "Category": row["category"],
            "Row": row["row_label"],
            "Seat": row["seat_number"],
            "Price": format_kzt(row["price_kzt"]),
            "Status": row["status"],
        }
        for row in rows
    ]
    render_table(formatted)


def rows_to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
