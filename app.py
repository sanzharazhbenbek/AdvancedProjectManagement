from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page
from core.navigation import page_for_route


def main() -> None:
    bootstrap_page("EventSphere", sidebar_state="collapsed")
    route = str(st.query_params.get("route", "discover"))
    st.switch_page(page_for_route(route))


if __name__ == "__main__":
    main()
