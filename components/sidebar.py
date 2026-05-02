from __future__ import annotations

import streamlit as st

from core.navigation import ROUTE_TO_PAGE
from core.session import navigate_to
from components.layout import render_brand_sidebar
from services.auth_service import sign_out


def render_sidebar(current_user: dict | None) -> None:
    with st.sidebar:
        render_brand_sidebar()
        if current_user is None:
            _public_links()
            return

        st.caption(f"{current_user['full_name']}")
        st.caption(f"{current_user['role_label']} • {current_user['email']}")
        st.divider()

        if current_user["role"] == "user":
            _user_links()
        elif current_user["role"] == "organizer":
            _organizer_links()
        else:
            _admin_links()

        st.divider()
        if st.button("Sign out", width="stretch"):
            sign_out()
            navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")


def _public_links() -> None:
    _nav_button("Discover events", "discover")
    _nav_button("Sign in", "sign_in")
    _nav_button("Create account", "create_account")


def _user_links() -> None:
    _nav_button("Discover events", "discover")
    _nav_button("My tickets", "user_dashboard")


def _organizer_links() -> None:
    _nav_button("Discover events", "discover")
    _nav_button("Organizer dashboard", "organizer_dashboard")
    _nav_button("Create event", "create_event")
    _nav_button("My events", "my_events")
    _nav_button("Sales / attendance reports", "organizer_reports")


def _admin_links() -> None:
    _nav_button("Admin dashboard", "admin_dashboard")
    _nav_button("Manage users", "manage_users")
    _nav_button("Manage events", "manage_events")
    _nav_button("Reports", "admin_reports")


def _nav_button(label: str, route: str) -> None:
    if st.button(label, key=f"nav-{route}", width="stretch"):
        navigate_to(ROUTE_TO_PAGE[route], route=route)
