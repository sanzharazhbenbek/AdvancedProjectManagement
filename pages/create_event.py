from __future__ import annotations

import streamlit as st

from components.forms import render_event_form
from components.layout import bootstrap_page, render_page_header
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.auth_service import get_current_user
from services.event_service import create_event


def render_page() -> None:
    bootstrap_page("Create Event")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to create events.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "organizer":
        flash("warning", "Only organizers can create events.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    render_page_header(
        "Create a realistic event",
        "Add scheduling, inventory, pricing, venue details, and a strong event description for attendees.",
    )

    payload = render_event_form(submit_label="Publish event", key_prefix="create_event_form")
    if payload is None:
        return

    event, errors = create_event(current_user, payload)
    if errors:
        for error in errors:
            st.error(error)
        return

    flash("success", "Event published successfully.")
    navigate_to(ROUTE_TO_PAGE["my_events"], route="my_events", event_id=event["id"])


render_page()
