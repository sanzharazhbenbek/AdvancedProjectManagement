from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE, default_route_for_role
from core.session import consume_redirect, navigate_to
from services.auth_service import get_current_user, sign_in
from utils.validators import validate_sign_in


def render_page() -> None:
    bootstrap_page("Sign In")
    current_user = get_current_user()
    if current_user is not None:
        route = default_route_for_role(current_user["role"])
        navigate_to(ROUTE_TO_PAGE[route], route=route)

    render_sidebar(None)
    render_page_header(
        "Welcome back",
        "Sign in to continue your booking, manage your events, or work through organizer and admin tools.",
    )

    with st.form("sign_in_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", width="stretch")

    if submitted:
        errors = validate_sign_in(email, password)
        if not errors:
            user, auth_errors = sign_in(email, password)
            errors.extend(auth_errors)
            if user is not None and not errors:
                redirect = consume_redirect()
                if redirect:
                    navigate_to(redirect["page"], **redirect["params"])
                route = default_route_for_role(user["role"])
                navigate_to(ROUTE_TO_PAGE[route], route=route)
        for error in errors:
            st.error(error)

    with st.expander("Seed accounts"):
        st.code(
            "\n".join(
                [
                    "Admin: admin@eventsphere.local / Admin123!",
                    "Organizer: organizer@eventsphere.local / Organizer123!",
                    "User: user@eventsphere.local / User123!",
                ]
            )
        )


render_page()
