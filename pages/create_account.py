from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_page_header
from components.sidebar import render_sidebar
from core.navigation import ROUTE_TO_PAGE, default_route_for_role
from core.session import consume_redirect, navigate_to
from services.auth_service import get_current_user, register_user
from utils.validators import validate_registration


def render_page() -> None:
    bootstrap_page("Create Account")
    current_user = get_current_user()
    if current_user is not None:
        route = default_route_for_role(current_user["role"])
        navigate_to(ROUTE_TO_PAGE[route], route=route)

    render_sidebar(None)
    render_page_header(
        "Create your EventSphere account",
        "Start as a member or organizer and move through a realistic Streamlit-based ticketing workflow.",
    )

    with st.form("register_form"):
        full_name = st.text_input("Full name")
        email = st.text_input("Email")
        role = st.selectbox("Account type", options=["user", "organizer"], format_func=lambda item: item.title())
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", width="stretch", type="primary")

    if submitted:
        errors = validate_registration(full_name, email, password, confirm_password, role)
        if not errors:
            user, registration_errors = register_user(full_name, email, password, role)
            errors.extend(registration_errors)
            if user is not None and not errors:
                redirect = consume_redirect()
                if redirect:
                    navigate_to(redirect["page"], **redirect["params"])
                route = default_route_for_role(user["role"])
                navigate_to(ROUTE_TO_PAGE[route], route=route)
        for error in errors:
            st.error(error)


render_page()
