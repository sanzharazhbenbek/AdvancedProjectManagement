from __future__ import annotations

import streamlit as st

from core.session import pop_flashes


ALERT_MAP = {
    "success": st.success,
    "warning": st.warning,
    "error": st.error,
    "info": st.info,
}


def render_flash_messages() -> None:
    for item in pop_flashes():
        renderer = ALERT_MAP.get(item["level"], st.info)
        renderer(item["message"])
