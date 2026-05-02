from __future__ import annotations

import streamlit as st

from components.cards import render_event_card, render_featured_event
from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import navigate_to, set_selected_event
from services.auth_service import get_current_user
from services.event_service import list_discover_events


def render_page() -> None:
    bootstrap_page("Discover Events")
    current_user = get_current_user()
    render_sidebar(current_user)

    sort_options = {
        "Date": "date",
        "Price": "price",
        "Popularity": "popularity",
        "Remaining tickets": "remaining",
    }
    date_options = {"Upcoming": "upcoming", "Past": "past", "All": "all"}

    filter_columns = st.columns([2, 1, 1, 1], gap="medium")
    search = filter_columns[0].text_input("Search", placeholder="Search by title, category, city, or venue")
    date_scope = filter_columns[3].selectbox("Date", options=list(date_options))
    sort_label = st.selectbox("Sort by", options=list(sort_options), index=0)

    catalog = list_discover_events(
        {
            "search": search,
            "date_scope": date_options[date_scope],
            "sort_by": sort_options[sort_label],
        },
        viewer_id=current_user["id"] if current_user else None,
    )

    category = filter_columns[1].selectbox("Category", options=["All", *catalog["categories"]], index=0, key="category_filter")
    city = filter_columns[2].selectbox("City", options=["All", *catalog["cities"]], index=0, key="city_filter")
    catalog = list_discover_events(
        {
            "search": search,
            "category": category,
            "city": city,
            "date_scope": date_options[date_scope],
            "sort_by": sort_options[sort_label],
        },
        viewer_id=current_user["id"] if current_user else None,
    )

    render_page_header(
        "Discover events in Kazakhstan",
        "Explore realistic upcoming events, review venue details, and move from browsing to QR ticketing in a clean production-like flow.",
        stats=[
            {"label": "Listed events", "value": catalog["stats"]["total_events"]},
            {"label": "Upcoming", "value": catalog["stats"]["upcoming_events"]},
            {"label": "Sold out", "value": catalog["stats"]["sold_out_events"]},
            {"label": "Cities", "value": catalog["stats"]["cities"]},
        ],
    )

    st.subheader("Featured event")
    if catalog["featured"] and render_featured_event(catalog["featured"]):
        _open_event(catalog["featured"]["id"])

    st.subheader("All events")
    if not catalog["events"]:
        render_empty_state("No events match your current filters.", "Try widening the date range or clearing one of the filters.")
        return

    columns = st.columns(3, gap="large")
    for index, event in enumerate(catalog["events"]):
        with columns[index % 3]:
            if render_event_card(event, key_prefix="discover"):
                _open_event(event["id"])


def _open_event(event_id: int) -> None:
    set_selected_event(event_id)
    navigate_to(ROUTE_TO_PAGE["event_detail"], route="event_detail", event_id=event_id)


render_page()
