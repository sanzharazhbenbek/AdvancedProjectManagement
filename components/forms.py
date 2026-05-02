from __future__ import annotations

from datetime import time
from typing import Any

import streamlit as st

from utils.date_utils import combine_date_and_time, now_local
from utils.validators import CATEGORY_OPTIONS, CITY_OPTIONS


def render_event_form(defaults: dict[str, Any] | None = None, submit_label: str = "Save event", key_prefix: str = "event_form"):
    defaults = defaults or {}
    reference_time = defaults.get("event_datetime") or now_local()

    with st.form(key_prefix):
        title = st.text_input("Event title", value=defaults.get("title", ""))
        option_columns = st.columns(2)
        category = option_columns[0].selectbox(
            "Category",
            options=CATEGORY_OPTIONS,
            index=_safe_index(CATEGORY_OPTIONS, defaults.get("category", CATEGORY_OPTIONS[0])),
        )
        city = option_columns[1].selectbox(
            "City",
            options=CITY_OPTIONS,
            index=_safe_index(CITY_OPTIONS, defaults.get("city", CITY_OPTIONS[0])),
        )
        venue = st.text_input("Venue", value=defaults.get("venue", ""))
        datetime_columns = st.columns(2)
        event_date = datetime_columns[0].date_input("Event date", value=reference_time.date())
        event_time = datetime_columns[1].time_input("Event time", value=reference_time.time().replace(second=0, microsecond=0) or time(18, 0))
        pricing_columns = st.columns(2)
        price_kzt = pricing_columns[0].number_input(
            "Ticket price (KZT)",
            min_value=0,
            value=int(defaults.get("price_kzt", 10000)),
            step=1000,
        )
        capacity = pricing_columns[1].number_input(
            "Capacity",
            min_value=1,
            value=int(defaults.get("capacity", 100)),
            step=1,
        )
        image_url = st.text_input("Cover image URL", value=defaults.get("image_url", ""))
        description = st.text_area("Description", value=defaults.get("description", ""), height=180)
        submitted = st.form_submit_button(submit_label, width="stretch")

    if not submitted:
        return None

    return {
        "title": title,
        "category": category,
        "city": city,
        "venue": venue,
        "event_datetime": combine_date_and_time(event_date, event_time),
        "price_kzt": int(price_kzt),
        "capacity": int(capacity),
        "image_url": image_url,
        "description": description,
    }


def _safe_index(options: list[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0
