from __future__ import annotations

from typing import Any

import streamlit as st

from components.alerts import render_flash_messages
from core.config import settings
from core.session import initialize_session_state
from db.seed import initialize_database
from utils.formatters import format_percent


GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
  --bg: #f5efe5;
  --surface: rgba(255, 255, 255, 0.86);
  --card: rgba(255, 255, 255, 0.94);
  --line: rgba(16, 28, 33, 0.10);
  --text: #152126;
  --muted: #607078;
  --accent: #e3642a;
  --accent-dark: #9f3d19;
  --success: #228168;
  --warning: #e3a420;
  --danger: #c45239;
}

.stApp {
  background:
    radial-gradient(circle at top left, rgba(227, 100, 42, 0.14), transparent 23%),
    radial-gradient(circle at top right, rgba(34, 129, 104, 0.12), transparent 18%),
    linear-gradient(180deg, #fffaf4 0%, var(--bg) 100%);
}

html, body, [class*="css"] {
  font-family: "Manrope", "Segoe UI", sans-serif;
  color: var(--text);
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #142127 0%, #1f3137 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

[data-testid="stSidebar"] * {
  color: #f8f3ea;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  color: inherit;
}

.brand-card {
  padding: 1rem 1.1rem;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(255,255,255,0.14), rgba(255,255,255,0.06));
  border: 1px solid rgba(255,255,255,0.12);
  margin-bottom: 1rem;
}

.brand-card h2 {
  margin: 0;
  font-size: 1.35rem;
}

.brand-card p {
  margin: 0.35rem 0 0;
  font-size: 0.92rem;
  color: rgba(248,243,234,0.82);
}

.page-hero {
  background: linear-gradient(135deg, rgba(21,33,38,0.96), rgba(31,49,55,0.92));
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 28px;
  padding: 1.75rem;
  box-shadow: 0 18px 48px rgba(21,33,38,0.16);
  color: #fff8f0;
  margin-bottom: 1rem;
}

.page-hero h1 {
  margin: 0;
  font-size: 2.2rem;
}

.page-hero p {
  margin: 0.55rem 0 0;
  max-width: 760px;
  color: rgba(255,248,240,0.82);
}

.pill {
  display: inline-block;
  border-radius: 999px;
  padding: 0.28rem 0.72rem;
  font-size: 0.78rem;
  font-weight: 800;
  margin: 0 0.35rem 0.35rem 0;
}

.pill-category {
  background: rgba(227, 100, 42, 0.14);
  color: var(--accent-dark);
}

.pill-upcoming {
  background: rgba(34, 129, 104, 0.16);
  color: var(--success);
}

.pill-sold_out {
  background: rgba(227, 164, 32, 0.16);
  color: #8c6300;
}

.pill-past {
  background: rgba(96, 112, 120, 0.16);
  color: #4f6168;
}

.pill-cancelled {
  background: rgba(196, 82, 57, 0.16);
  color: var(--danger);
}

.surface-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 1rem 1.05rem;
  box-shadow: 0 12px 32px rgba(21,33,38,0.06);
}

.muted {
  color: var(--muted);
}

.section-title {
  margin-top: 0.35rem;
}

.info-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 1rem;
}

.info-tile {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 18px;
  padding: 0.85rem;
}

.info-tile strong {
  display: block;
  font-size: 1.05rem;
  color: #fff8f0;
}

.info-tile span {
  font-size: 0.82rem;
  color: rgba(255,248,240,0.74);
}

.empty-state {
  padding: 1.4rem;
  border-radius: 24px;
  border: 1px dashed rgba(21,33,38,0.18);
  background: rgba(255,255,255,0.58);
}

div[data-testid="stMetric"] {
  background: rgba(255,255,255,0.86);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 0.9rem 1rem;
}
</style>
"""


def bootstrap_page(page_title: str, sidebar_state: str = "expanded") -> None:
    st.set_page_config(
        page_title=f"{page_title} • {settings.brand_name}",
        page_icon="T",
        layout="wide",
        initial_sidebar_state=sidebar_state,
    )
    initialize_session_state()
    initialize_database()
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    render_flash_messages()


def render_brand_sidebar() -> None:
    st.markdown(
        """
        <div class="brand-card">
          <h2>EventSphere</h2>
          <p>Ticketing, QR access, sandbox payments, and attendance workflows in one Streamlit app.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, stats: list[dict[str, Any]] | None = None) -> None:
    stat_html = ""
    if stats:
        tiles = "".join(
            f'<div class="info-tile"><strong>{item["value"]}</strong><span>{item["label"]}</span></div>' for item in stats
        )
        stat_html = f'<div class="info-strip">{tiles}</div>'

    st.markdown(
        f"""
        <section class="page-hero">
          <h1>{title}</h1>
          <p>{subtitle}</p>
          {stat_html}
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_status_pills(category: str | None = None, status: str | None = None) -> None:
    fragments: list[str] = []
    if category:
        fragments.append(f'<span class="pill pill-category">{category}</span>')
    if status:
        fragments.append(f'<span class="pill pill-{status}">{status.replace("_", " ").title()}</span>')
    if fragments:
        st.markdown("".join(fragments), unsafe_allow_html=True)


def render_kpi_row(metrics: list[dict[str, Any]]) -> None:
    columns = st.columns(len(metrics))
    for column, metric in zip(columns, metrics):
        with column:
            st.metric(metric["label"], metric["value"], delta=metric.get("delta"))


def render_empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="empty-state">
          <strong>{title}</strong>
          <p class="muted" style="margin-bottom:0;">{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fill_rate_label(value: float) -> str:
    return format_percent(value)
