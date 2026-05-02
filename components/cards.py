from __future__ import annotations

import streamlit as st

from components.layout import render_status_pills
from utils.formatters import format_datetime, format_kzt


def render_featured_event(event: dict) -> bool:
    if not event:
        return False

    left, right = st.columns([1.25, 1], gap="large")
    with left:
        if event.get("image_url"):
            st.image(event["image_url"], width="stretch")
    with right:
        render_status_pills(event.get("category"), event.get("runtime_status"))
        st.subheader(event["title"])
        st.write(event["description"])
        st.caption(f"{format_datetime(event['event_datetime'])} • {event['venue']}, {event['city']}")
        stats = st.columns(3)
        stats[0].metric("Price", format_kzt(event["price_kzt"]))
        stats[1].metric("Remaining", str(event["remaining_count"]))
        stats[2].metric("Sold", str(event["sold_count"]))
        return st.button("Open featured event", key=f"featured-{event['id']}", width="stretch")

    return False


def render_event_card(event: dict, key_prefix: str = "event") -> bool:
    with st.container(border=True):
        if event.get("image_url"):
            st.image(event["image_url"], width="stretch")
        render_status_pills(event.get("category"), event.get("runtime_status"))
        st.markdown(f"#### {event['title']}")
        st.caption(f"{format_datetime(event['event_datetime'])} • {event['venue']}, {event['city']}")
        st.caption(event["description"][:160] + ("..." if len(event["description"]) > 160 else ""))
        stats = st.columns(2)
        stats[0].metric("Price", format_kzt(event["price_kzt"]))
        stats[1].metric("Remaining", str(event["remaining_count"]))
        return st.button("Open details", key=f"{key_prefix}-{event['id']}", width="stretch")


def render_ticket_card(ticket: dict) -> tuple[bool, bool]:
    with st.container(border=True):
        render_status_pills(ticket["event"].get("category"), ticket.get("status"))
        st.markdown(f"#### {ticket['event']['title']}")
        st.caption(f"{format_datetime(ticket['event']['event_datetime'])} • {ticket['event']['venue']}, {ticket['event']['city']}")
        st.code(ticket["ticket_code"])
        left, right = st.columns(2)
        open_ticket = left.button("Open ticket", key=f"ticket-open-{ticket['id']}", width="stretch")
        open_event = right.button("View event", key=f"ticket-event-{ticket['id']}", width="stretch")
        return open_ticket, open_event
