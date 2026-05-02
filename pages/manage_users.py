from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page, render_empty_state, render_page_header
from components.sidebar import render_sidebar
from components.tables import render_table
from core.navigation import ROUTE_TO_PAGE
from core.session import flash, navigate_to
from services.auth_service import get_current_user
from services.event_service import deactivate_user, list_all_user_rows
from utils.formatters import role_label


def render_page() -> None:
    bootstrap_page("Manage Users")
    current_user = get_current_user()
    if current_user is None:
        flash("warning", "Sign in to access user management.")
        navigate_to(ROUTE_TO_PAGE["sign_in"], route="sign_in")
    if current_user["role"] != "admin":
        flash("warning", "Only admins can access this page.")
        navigate_to(ROUTE_TO_PAGE["discover"], route="discover")

    render_sidebar(current_user)
    users = list_all_user_rows()
    render_page_header("Manage users", "Review accounts, roles, activity status, and deactivate users when needed.")

    if not users:
        render_empty_state("No users found", "User accounts will appear here after registration or seeding.")
        return

    render_table(
        [
            {
                "ID": user["id"],
                "Name": user["full_name"],
                "Email": user["email"],
                "Role": role_label(user["role"]),
                "Active": user["is_active"],
            }
            for user in users
        ]
    )

    selected_user_id = st.selectbox(
        "Choose a user",
        options=[user["id"] for user in users],
        format_func=lambda value: next(f"{user['full_name']} • {user['email']}" for user in users if user["id"] == value),
    )
    selected_user = next(user for user in users if user["id"] == selected_user_id)
    st.write(f"**Role:** {role_label(selected_user['role'])}")
    st.write(f"**Status:** {'Active' if selected_user['is_active'] else 'Inactive'}")
    if selected_user["is_active"] and st.button("Deactivate user", width="stretch"):
        success, message = deactivate_user(current_user, selected_user_id)
        if success:
            flash("warning", message)
            navigate_to(ROUTE_TO_PAGE["manage_users"], route="manage_users")
        st.error(message)


render_page()
