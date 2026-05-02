from __future__ import annotations

import streamlit as st

from components.layout import bootstrap_page
from core.navigation import page_for_route
from core.session import get_query_param, sync_query_params_to_session


def main() -> None:
    bootstrap_page("EventSphere", sidebar_state="collapsed")
    sync_query_params_to_session()
    route = str(get_query_param("route", "discover"))
    st.switch_page(page_for_route(route))


if __name__ == "__main__":
    main()
