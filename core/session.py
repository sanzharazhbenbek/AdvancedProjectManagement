from __future__ import annotations

from typing import Any

import streamlit as st

from core.config import settings


def initialize_session_state() -> None:
    st.session_state.setdefault(settings.session_flash_key, [])
    st.session_state.setdefault(settings.session_redirect_key, None)
    st.session_state.setdefault(settings.session_selected_event_key, None)
    st.session_state.setdefault(settings.session_selected_booking_key, None)
    st.session_state.setdefault(settings.session_selected_ticket_key, None)
    st.session_state.setdefault(settings.session_route_params_key, {})


def set_user_id(user_id: int) -> None:
    st.session_state[settings.session_user_key] = user_id


def get_user_id() -> int | None:
    value = st.session_state.get(settings.session_user_key)
    return int(value) if value is not None else None


def clear_user() -> None:
    st.session_state.pop(settings.session_user_key, None)


def remember_redirect(page: str, **params: Any) -> None:
    st.session_state[settings.session_redirect_key] = {"page": page, "params": params}


def consume_redirect() -> dict[str, Any] | None:
    redirect = st.session_state.get(settings.session_redirect_key)
    st.session_state[settings.session_redirect_key] = None
    return redirect


def flash(level: str, message: str) -> None:
    queue = st.session_state.setdefault(settings.session_flash_key, [])
    queue.append({"level": level, "message": message})


def pop_flashes() -> list[dict[str, str]]:
    flashes = list(st.session_state.get(settings.session_flash_key, []))
    st.session_state[settings.session_flash_key] = []
    return flashes


def set_selected_event(event_id: int | None) -> None:
    st.session_state[settings.session_selected_event_key] = event_id


def get_selected_event() -> int | None:
    value = st.session_state.get(settings.session_selected_event_key)
    return int(value) if value is not None else None


def set_selected_booking(booking_id: int | None) -> None:
    st.session_state[settings.session_selected_booking_key] = booking_id


def get_selected_booking() -> int | None:
    value = st.session_state.get(settings.session_selected_booking_key)
    return int(value) if value is not None else None


def set_selected_ticket(ticket_id: int | None) -> None:
    st.session_state[settings.session_selected_ticket_key] = ticket_id


def get_selected_ticket() -> int | None:
    value = st.session_state.get(settings.session_selected_ticket_key)
    return int(value) if value is not None else None


def set_query_params(**params: Any) -> None:
    stored_params: dict[str, str] = {}
    st.query_params.clear()
    for key, value in params.items():
        if value is None:
            continue
        stored_value = str(value)
        stored_params[key] = stored_value
        st.query_params[key] = stored_value
    st.session_state[settings.session_route_params_key] = stored_params


def sync_query_params_to_session() -> None:
    st.session_state[settings.session_route_params_key] = {key: str(st.query_params.get(key)) for key in st.query_params}


def get_query_param(name: str, default: str | None = None) -> str | None:
    raw_value = st.query_params.get(name)
    if raw_value not in {None, ""}:
        return str(raw_value)
    stored_params = st.session_state.get(settings.session_route_params_key, {})
    stored_value = stored_params.get(name)
    if stored_value not in {None, ""}:
        return str(stored_value)
    return default


def navigate_to(page: str, **params: Any) -> None:
    set_query_params(**params)
    st.switch_page(page)
