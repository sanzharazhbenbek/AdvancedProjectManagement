from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from html import escape
from typing import Any

import streamlit as st
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import Base, build_engine, build_session_factory
from app.main import (
    ROLE_LABELS,
    build_attention_events,
    build_recommended_events,
    build_report_insights,
    build_report_statement,
    build_system_stats,
    can_manage_event,
    can_validate_ticket,
    count_active_admins,
    format_datetime,
    format_money,
    generate_qr_svg_data_uri,
    generate_ticket_code,
    get_checked_in_quantity_for_event,
    get_checked_in_ticket_map,
    get_recent_tickets_for_scope,
    get_sold_quantity_for_event,
    get_sold_ticket_map,
    get_visible_events,
    is_booking_open,
    migrate_existing_schema,
    prepare_event_card,
    validate_booking_form,
    validate_event_form,
)
from app.models import Event, Ticket, User
from app.security import hash_password, normalize_email, verify_password
from app.seed import seed_default_users


st.set_page_config(
    page_title="EventSphere",
    page_icon="T",
    layout="wide",
    initial_sidebar_state="expanded",
)


PAYMENT_METHODS = ["Kaspi Pay", "Bank Card", "Cash at venue"]
NOTICE_TYPES = {
    "success": st.success,
    "warning": st.warning,
    "danger": st.error,
    "info": st.info,
}


APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');

:root {
  --bg: #f6f1e8;
  --surface: rgba(255, 255, 255, 0.82);
  --card: rgba(255, 255, 255, 0.92);
  --ink: #172321;
  --muted: #5f6d68;
  --accent: #d9672f;
  --accent-dark: #9f3e18;
  --line: rgba(23, 35, 33, 0.12);
  --success: #2d8f6f;
  --live: #b3451c;
}

.stApp {
  background:
    radial-gradient(circle at top left, rgba(217, 103, 47, 0.14), transparent 26%),
    radial-gradient(circle at top right, rgba(45, 143, 111, 0.14), transparent 22%),
    linear-gradient(180deg, #fcfaf6 0%, var(--bg) 100%);
  color: var(--ink);
}

html, body, [class*="css"]  {
  font-family: "Space Grotesk", "Segoe UI", sans-serif;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #13211f 0%, #1b2b28 100%);
}

[data-testid="stSidebar"] * {
  color: #f8f4eb;
}

.hero {
  background: linear-gradient(135deg, rgba(19, 33, 31, 0.96), rgba(28, 46, 42, 0.9));
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 28px;
  padding: 28px 30px;
  color: #fff8ef;
  box-shadow: 0 18px 60px rgba(19, 33, 31, 0.18);
  margin-bottom: 1rem;
}

.hero h1 {
  margin: 0 0 0.35rem 0;
  font-size: 2.4rem;
}

.hero p {
  margin: 0;
  color: rgba(255, 248, 239, 0.82);
  max-width: 760px;
}

.section-title {
  margin-top: 0.7rem;
  margin-bottom: 0.25rem;
}

.event-card,
.surface-card,
.ticket-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 18px 18px 16px 18px;
  box-shadow: 0 10px 30px rgba(23, 35, 33, 0.06);
}

.event-meta,
.muted {
  color: var(--muted);
}

.pill-row {
  margin-bottom: 0.55rem;
}

.pill {
  display: inline-block;
  padding: 0.28rem 0.72rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  margin-right: 0.35rem;
  margin-bottom: 0.3rem;
}

.pill-status-upcoming {
  background: rgba(45, 143, 111, 0.13);
  color: var(--success);
}

.pill-status-live {
  background: rgba(179, 69, 28, 0.13);
  color: var(--live);
}

.pill-status-completed {
  background: rgba(95, 109, 104, 0.14);
  color: var(--muted);
}

.pill-category {
  background: rgba(217, 103, 47, 0.12);
  color: var(--accent-dark);
}

.mini-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 0.8rem;
}

.mini-stat {
  background: rgba(246, 241, 232, 0.7);
  border: 1px solid rgba(23, 35, 33, 0.08);
  border-radius: 16px;
  padding: 0.8rem;
}

.mini-stat-label {
  color: var(--muted);
  font-size: 0.82rem;
}

.mini-stat-value {
  font-size: 1.05rem;
  font-weight: 700;
  margin-top: 0.15rem;
}

.brand-lockup {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 22px;
  padding: 16px 16px 14px 16px;
  margin-bottom: 1rem;
}

.brand-lockup h2 {
  margin: 0 0 0.25rem 0;
  font-size: 1.35rem;
}

.brand-lockup p {
  margin: 0;
  color: rgba(248, 244, 235, 0.76);
}

.profile-card {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  padding: 14px;
  margin: 1rem 0;
}

.profile-card .role-pill {
  display: inline-block;
  padding: 0.24rem 0.6rem;
  border-radius: 999px;
  background: rgba(248, 244, 235, 0.18);
  margin-top: 0.35rem;
  font-size: 0.78rem;
}

.qr-wrap {
  background: white;
  border-radius: 20px;
  padding: 14px;
  border: 1px solid var(--line);
  text-align: center;
}

.empty-state {
  background: rgba(255, 255, 255, 0.68);
  border: 1px dashed rgba(23, 35, 33, 0.18);
  border-radius: 20px;
  padding: 18px;
  color: var(--muted);
}
</style>
"""


@st.cache_resource
def get_session_factory():
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    migrate_existing_schema(engine)
    SessionLocal = build_session_factory(engine)
    with SessionLocal() as session:
        seed_default_users(session)
    return SessionLocal


@contextmanager
def db_session():
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_state() -> None:
    defaults = {
        "user_id": None,
        "nav_page": "Discover events",
        "selected_event_id": None,
        "selected_ticket_code": None,
        "event_search": "",
        "checkin_code": "",
        "notices": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def add_notice(kind: str, message: str) -> None:
    st.session_state.notices.append((kind, message))


def show_notices() -> None:
    notices = st.session_state.get("notices", [])
    for kind, message in notices:
        NOTICE_TYPES.get(kind, st.info)(message)
    st.session_state.notices = []


def current_user(db: Session) -> User | None:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        st.session_state.user_id = None
        return None
    return user


def go_to(page: str) -> None:
    st.session_state.nav_page = page


def logout() -> None:
    st.session_state.user_id = None
    st.session_state.selected_ticket_code = None
    go_to("Discover events")
    add_notice("success", "You have been signed out.")
    st.rerun()


def render_app_style() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def h(value: Any) -> str:
    return escape(str(value), quote=True)


def render_sidebar(user: User | None) -> None:
    st.sidebar.markdown(
        """
        <div class="brand-lockup">
          <h2>EventSphere</h2>
          <p>Free-to-deploy Streamlit MVP for event booking, QR tickets, and attendance tracking.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if user is None:
        st.sidebar.caption("Browse events as a guest or sign in to book tickets.")
    else:
        st.sidebar.markdown(
            f"""
            <div class="profile-card">
              <strong>{h(user.full_name)}</strong><br>
              <span>{h(user.email)}</span><br>
              <span class="role-pill">{h(ROLE_LABELS.get(user.role, user.role.title()))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.sidebar.button("Log out", use_container_width=True):
            logout()

    pages = ["Discover events"]
    if user is None:
        pages.extend(["Sign in", "Create account"])
    else:
        pages.append("My tickets")
        if user.role in {"organizer", "admin"}:
            pages.append("Organizer workspace")
        if user.role == "admin":
            pages.append("Admin console")

    if st.session_state.nav_page not in pages:
        st.session_state.nav_page = pages[0]

    st.sidebar.radio("Navigate", pages, key="nav_page")
    st.sidebar.caption(f"Timezone: {settings.timezone_label}")


def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
          <h1>{h(title)}</h1>
          <p>{h(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(stats: dict[str, Any]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Events", stats["total_events"])
    col2.metric("Tickets sold", stats["tickets_sold"])
    col3.metric("Checked in", stats["checked_in"])
    col4.metric("Revenue", format_money(stats["revenue"]))


def fetch_events(db: Session, query: str = "") -> list[Event]:
    stmt = select(Event).order_by(Event.event_date.asc())
    if query:
        search = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Event.title.ilike(search),
                Event.category.ilike(search),
                Event.city.ilike(search),
                Event.venue.ilike(search),
            )
        )

    events = db.scalars(stmt).all()
    sold_map = get_sold_ticket_map(db)
    checked_map = get_checked_in_ticket_map(db)
    return [prepare_event_card(event, sold_map.get(event.id, 0), checked_map.get(event.id, 0)) for event in events]


def fetch_event_by_id(db: Session, event_id: int | None) -> Event | None:
    if event_id is None:
        return None
    event = db.get(Event, event_id)
    if event is None:
        return None
    sold = get_sold_quantity_for_event(db, event.id)
    checked_in = get_checked_in_quantity_for_event(db, event.id)
    return prepare_event_card(event, sold, checked_in)


def fetch_ticket_by_code(db: Session, ticket_code: str | None) -> Ticket | None:
    if not ticket_code:
        return None
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.event), selectinload(Ticket.purchaser))
        .where(Ticket.ticket_code == ticket_code)
    )
    return db.scalar(stmt)


def create_account(db: Session, full_name: str, email: str, password: str, confirm_password: str, role: str) -> None:
    email = normalize_email(email)
    errors: list[str] = []

    if not full_name.strip():
        errors.append("Full name is required.")
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if role not in {"user", "organizer"}:
        errors.append("Select a valid account type.")
    if len(password) < 8:
        errors.append("Password must contain at least 8 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if db.scalar(select(User.id).where(User.email == email)):
        errors.append("An account with this email already exists.")

    if errors:
        for error in errors:
            st.error(error)
        return

    user = User(
        full_name=full_name.strip(),
        email=email,
        password_hash=hash_password(password),
        role="admin" if email in settings.admin_emails else role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    st.session_state.user_id = user.id
    if user.role == "admin":
        go_to("Admin console")
    elif user.role == "organizer":
        go_to("Organizer workspace")
    else:
        go_to("My tickets")
    add_notice("success", f"Welcome to EventSphere, {user.full_name}.")
    st.rerun()


def sign_in(db: Session, email: str, password: str) -> None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not verify_password(password, user.password_hash):
        st.error("Invalid email or password.")
        return
    if not user.is_active:
        st.error("This account is currently inactive.")
        return

    st.session_state.user_id = user.id
    if user.role == "admin":
        go_to("Admin console")
    elif user.role == "organizer":
        go_to("Organizer workspace")
    else:
        go_to("My tickets")
    add_notice("success", f"Welcome back, {user.full_name}.")
    st.rerun()


def render_event_card(event: Event, user: User | None) -> None:
    left, right = st.columns([1.5, 1])
    with left:
        st.markdown(
            f"""
            <div class="event-card">
              <div class="pill-row">
                <span class="pill pill-category">{h(event.category)}</span>
                <span class="pill pill-status-{h(event.status_label.lower())}">{h(event.status_label)}</span>
              </div>
              <h3>{h(event.title)}</h3>
              <p class="event-meta">{h(format_datetime(event.event_date))} | {h(event.venue)}, {h(event.city)}</p>
              <p>{h(event.description[:180])}{'...' if len(event.description) > 180 else ''}</p>
              <div class="mini-stats">
                <div class="mini-stat">
                  <div class="mini-stat-label">Price</div>
                  <div class="mini-stat-value">{format_money(event.ticket_price)}</div>
                </div>
                <div class="mini-stat">
                  <div class="mini-stat-label">Remaining</div>
                  <div class="mini-stat-value">{event.remaining_capacity}</div>
                </div>
                <div class="mini-stat">
                  <div class="mini-stat-label">Fill rate</div>
                  <div class="mini-stat-value">{event.fill_rate}%</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        if event.image_url:
            st.image(event.image_url, use_container_width=True)
        else:
            st.markdown('<div class="empty-state">No event cover image provided yet.</div>', unsafe_allow_html=True)
        if st.button("Open details", key=f"open-event-{event.id}", use_container_width=True):
            st.session_state.selected_event_id = event.id
            st.rerun()
        if user and can_manage_event(user, event):
            if st.button("Manage this event", key=f"manage-event-{event.id}", use_container_width=True):
                st.session_state.selected_event_id = event.id
                go_to("Organizer workspace")
                st.rerun()


def render_event_detail(db: Session, event: Event, user: User | None) -> None:
    st.markdown("### Event details")
    left, right = st.columns([1.55, 1])

    with left:
        st.markdown(
            f"""
            <div class="surface-card">
              <div class="pill-row">
                <span class="pill pill-category">{h(event.category)}</span>
                <span class="pill pill-status-{h(event.status_label.lower())}">{h(event.status_label)}</span>
              </div>
              <h2>{h(event.title)}</h2>
              <p class="muted">{h(event.organizer_name)} | {h(format_datetime(event.event_date))} | {h(event.venue)}, {h(event.city)}</p>
              <p>{h(event.description)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        stats1, stats2, stats3, stats4 = st.columns(4)
        stats1.metric("Price", format_money(event.ticket_price))
        stats2.metric("Sold", event.sold_tickets)
        stats3.metric("Checked in", event.checked_in_tickets)
        stats4.metric("Remaining", event.remaining_capacity)

        related_events = build_recommended_events(db, event.id, event.category)
        if related_events:
            st.markdown("#### You may also like")
            for related in related_events:
                st.markdown(
                    f"- **{related.title}** on {format_datetime(related.event_date)} in {related.city}",
                )

    with right:
        if event.image_url:
            st.image(event.image_url, use_container_width=True)

        st.markdown("#### Book tickets")
        if user is None:
            st.info("Sign in first to complete a booking.")
            return

        if not is_booking_open(event):
            st.warning("Bookings are currently closed for this event.")
            return

        default_form = {"payment_method": PAYMENT_METHODS[0], "quantity": 1}
        with st.form(f"book-event-{event.id}"):
            quantity = st.number_input(
                "Tickets",
                min_value=1,
                max_value=max(1, min(event.remaining_capacity, 10)),
                value=min(default_form["quantity"], max(1, min(event.remaining_capacity, 10))),
                step=1,
            )
            payment_method = st.selectbox("Payment method", PAYMENT_METHODS, index=0)
            submitted = st.form_submit_button("Confirm booking", use_container_width=True)

        if submitted:
            booking_form, errors = validate_booking_form(
                {"payment_method": payment_method, "quantity": str(quantity)},
                user,
            )
            if booking_form["quantity"] > event.remaining_capacity:
                errors.append("Requested ticket quantity exceeds remaining capacity.")

            if errors:
                for error in errors:
                    st.error(error)
                return

            ticket = Ticket(
                event_id=event.id,
                purchaser_id=user.id,
                purchaser_name=user.full_name,
                purchaser_email=user.email,
                quantity=booking_form["quantity"],
                total_amount=event.ticket_price * booking_form["quantity"],
                payment_method=booking_form["payment_method"],
                payment_status="Confirmed",
                ticket_code=generate_ticket_code(db),
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)

            st.session_state.selected_ticket_code = ticket.ticket_code
            go_to("My tickets")
            add_notice("success", "Booking confirmed. Your digital ticket is ready.")
            st.rerun()


def render_ticket_view(ticket: Ticket) -> None:
    sold = ticket.quantity
    qr_data_uri = generate_qr_svg_data_uri(ticket.ticket_code)

    left, right = st.columns([1.4, 1])
    with left:
        st.markdown(
            f"""
            <div class="ticket-card">
              <h2>{h(ticket.event.title)}</h2>
              <p class="muted">{h(format_datetime(ticket.event.event_date))} | {h(ticket.event.venue)}, {h(ticket.event.city)}</p>
              <p><strong>Ticket code:</strong> {h(ticket.ticket_code)}</p>
              <p><strong>Attendee:</strong> {h(ticket.purchaser_name)} ({h(ticket.purchaser_email)})</p>
              <p><strong>Quantity:</strong> {sold}</p>
              <p><strong>Total paid:</strong> {format_money(ticket.total_amount)}</p>
              <p><strong>Payment method:</strong> {h(ticket.payment_method)}</p>
              <p><strong>Status:</strong> {'Checked in' if ticket.checked_in_at else 'Ready for entry'}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if ticket.checked_in_at:
            st.success(f"Checked in at {format_datetime(ticket.checked_in_at)}")

    with right:
        st.markdown(
            f"""
            <div class="qr-wrap">
              <img src="{qr_data_uri}" alt="QR code" style="width:100%; max-width:320px;" />
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("The QR code contains the ticket code for check-in.")


def render_discover_page(db: Session, user: User | None) -> None:
    render_hero(
        "Discover events without paying for hosting",
        "This Streamlit version keeps the same MVP idea from the project brief: organizers publish events, users book tickets, and staff validate entry with QR-based check-in.",
    )

    stats = build_system_stats(db)
    render_metrics(stats)

    st.text_input(
        "Search by title, category, city, or venue",
        key="event_search",
        placeholder="Try Technology, Almaty, auditorium, startup...",
    )
    events = fetch_events(db, st.session_state.event_search)

    featured_event = next((event for event in events if event.status_label == "Upcoming"), None)
    if featured_event is None and events:
        featured_event = events[0]

    if featured_event:
        st.markdown("### Featured event")
        st.markdown(
            f"""
            <div class="surface-card">
              <div class="pill-row">
                <span class="pill pill-category">{h(featured_event.category)}</span>
                <span class="pill pill-status-{h(featured_event.status_label.lower())}">{h(featured_event.status_label)}</span>
              </div>
              <h2>{h(featured_event.title)}</h2>
              <p class="muted">{h(format_datetime(featured_event.event_date))} | {h(featured_event.venue)}, {h(featured_event.city)}</p>
              <p>{h(featured_event.description)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### All events")
    if not events:
        st.markdown('<div class="empty-state">No events matched the current search.</div>', unsafe_allow_html=True)
        return

    for event in events:
        render_event_card(event, user)
        st.write("")

    selected_event = fetch_event_by_id(db, st.session_state.selected_event_id)
    if selected_event:
        render_event_detail(db, selected_event, user)


def render_sign_in_page(db: Session, user: User | None) -> None:
    render_hero(
        "Sign in",
        "Organizers can manage events and reports here, while attendees can book tickets and keep their QR passes in one place.",
    )
    if user is not None:
        st.info("You are already signed in.")
        return

    with st.form("sign-in-form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        sign_in(db, email, password)


def render_create_account_page(db: Session, user: User | None) -> None:
    render_hero(
        "Create your EventSphere account",
        "Use a regular user account to buy tickets or an organizer account to publish and manage events.",
    )
    if user is not None:
        st.info("You are already signed in.")
        return

    with st.form("create-account-form"):
        full_name = st.text_input("Full name")
        email = st.text_input("Email")
        role = st.selectbox("Account type", ["user", "organizer"], format_func=lambda value: ROLE_LABELS[value])
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True)

    if submitted:
        create_account(db, full_name, email, password, confirm_password, role)


def render_my_tickets_page(db: Session, user: User | None) -> None:
    render_hero(
        "My tickets",
        "Every confirmed booking generates a digital ticket code and QR entry pass that can be checked at the venue.",
    )
    if user is None:
        st.warning("Sign in to view your tickets.")
        return

    tickets = db.scalars(
        select(Ticket)
        .options(selectinload(Ticket.event), selectinload(Ticket.purchaser))
        .where(Ticket.purchaser_id == user.id)
        .order_by(Ticket.created_at.desc())
    ).all()

    sold_map = get_sold_ticket_map(db)
    checked_map = get_checked_in_ticket_map(db)
    for ticket in tickets:
        prepare_event_card(ticket.event, sold_map.get(ticket.event.id, 0), checked_map.get(ticket.event.id, 0))

    if not tickets:
        st.markdown('<div class="empty-state">You have not booked any tickets yet.</div>', unsafe_allow_html=True)
        return

    options = [ticket.ticket_code for ticket in tickets]
    if st.session_state.selected_ticket_code not in options:
        st.session_state.selected_ticket_code = options[0]

    selected_code = st.selectbox(
        "Choose a ticket",
        options,
        format_func=lambda code: next(
            f"{ticket.ticket_code} | {ticket.event.title} | {format_datetime(ticket.event.event_date)}"
            for ticket in tickets
            if ticket.ticket_code == code
        ),
        key="selected_ticket_code",
    )

    selected_ticket = next(ticket for ticket in tickets if ticket.ticket_code == selected_code)
    render_ticket_view(selected_ticket)


def event_form_defaults(current_user: User, event: Event | None = None) -> dict[str, Any]:
    default_time = (datetime.now() + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
    target = event.event_date if event else default_time
    return {
        "title": event.title if event else "",
        "category": event.category if event else "",
        "organizer_name": event.organizer_name if event else current_user.full_name,
        "venue": event.venue if event else "",
        "city": event.city if event else "Almaty",
        "description": event.description if event else "",
        "event_date": target.date(),
        "event_time": target.time().replace(second=0, microsecond=0),
        "ticket_price": float(event.ticket_price) if event else 10000.0,
        "capacity": int(event.capacity) if event else 100,
        "image_url": event.image_url or "" if event else "",
    }


def render_event_editor(db: Session, current_user: User, event: Event | None = None) -> None:
    defaults = event_form_defaults(current_user, event)
    form_key = f"event-editor-{event.id if event else 'new'}"

    with st.form(form_key):
        title = st.text_input("Title", value=defaults["title"])
        category = st.text_input("Category", value=defaults["category"])
        organizer_name = st.text_input("Organizer name", value=defaults["organizer_name"])
        venue = st.text_input("Venue", value=defaults["venue"])
        city = st.text_input("City", value=defaults["city"])
        description = st.text_area("Description", value=defaults["description"], height=160)
        event_cols = st.columns(2)
        event_date = event_cols[0].date_input("Event date", value=defaults["event_date"])
        event_time = event_cols[1].time_input("Start time", value=defaults["event_time"])
        commerce_cols = st.columns(2)
        ticket_price = commerce_cols[0].number_input(
            "Ticket price (KZT)",
            min_value=1.0,
            step=500.0,
            value=float(defaults["ticket_price"]),
        )
        capacity = commerce_cols[1].number_input(
            "Capacity",
            min_value=1,
            step=1,
            value=int(defaults["capacity"]),
        )
        image_url = st.text_input("Cover image URL", value=defaults["image_url"])
        submitted = st.form_submit_button(
            "Create event" if event is None else "Save changes",
            use_container_width=True,
        )

    if not submitted:
        return

    form_data, errors = validate_event_form(
        {
            "title": title,
            "category": category,
            "organizer_name": organizer_name,
            "venue": venue,
            "city": city,
            "description": description,
            "event_date": datetime.combine(event_date, event_time).strftime("%Y-%m-%dT%H:%M"),
            "ticket_price": str(ticket_price),
            "capacity": str(int(capacity)),
            "image_url": image_url,
        }
    )

    if not errors and event is not None:
        sold_tickets = get_sold_quantity_for_event(db, event.id)
        if form_data["capacity"] < sold_tickets:
            errors.append(f"Capacity cannot be lower than the {sold_tickets} tickets already sold.")

    if errors:
        for error in errors:
            st.error(error)
        return

    if event is None:
        record = Event(organizer_id=current_user.id, **form_data)
        db.add(record)
        db.commit()
        db.refresh(record)
        st.session_state.selected_event_id = record.id
        add_notice("success", "Event created successfully.")
    else:
        for key, value in form_data.items():
            setattr(event, key, value)
        db.add(event)
        db.commit()
        st.session_state.selected_event_id = event.id
        add_notice("success", "Event updated successfully.")

    go_to("Organizer workspace")
    st.rerun()


def render_check_in_panel(db: Session, current_user: User) -> None:
    with st.form("checkin-form"):
        code = st.text_input(
            "Enter or scan ticket code",
            value=st.session_state.checkin_code,
            placeholder="EVT-1234ABCD",
        )
        lookup = st.form_submit_button("Lookup ticket", use_container_width=True)

    if lookup:
        st.session_state.checkin_code = code.strip().upper()
        st.rerun()

    ticket = fetch_ticket_by_code(db, st.session_state.checkin_code)
    if not st.session_state.checkin_code:
        st.caption("Load a ticket code to validate entry.")
        return
    if ticket is None:
        st.error("Ticket not found.")
        return
    if not can_validate_ticket(current_user, ticket):
        st.error("You do not have permission to validate this ticket.")
        return

    render_ticket_view(ticket)
    if ticket.checked_in_at is not None:
        st.warning("This ticket was already checked in earlier.")
        return

    if st.button("Confirm check-in", key=f"checkin-{ticket.ticket_code}", use_container_width=True):
        ticket.checked_in_at = datetime.now()
        db.add(ticket)
        db.commit()
        add_notice("success", "Check-in completed successfully.")
        st.rerun()


def render_reports_panel(db: Session, current_user: User) -> None:
    organizer_scope_id = None if current_user.role == "admin" else current_user.id
    event_rows = db.execute(build_report_statement(organizer_scope_id)).all()

    report_rows: list[dict[str, Any]] = []
    for event, tickets_sold, checked_in, revenue in event_rows:
        tickets_sold = int(tickets_sold or 0)
        checked_in = int(checked_in or 0)
        revenue = float(revenue or 0.0)
        prepared_event = prepare_event_card(event, tickets_sold, checked_in)
        report_rows.append(
            {
                "event": prepared_event,
                "tickets_sold": tickets_sold,
                "checked_in": checked_in,
                "revenue": revenue,
                "fill_rate": round((tickets_sold / event.capacity) * 100) if event.capacity else 0,
                "attendance_rate": round((checked_in / tickets_sold) * 100) if tickets_sold else 0,
            }
        )

    if not report_rows:
        st.markdown('<div class="empty-state">No events are available for reporting yet.</div>', unsafe_allow_html=True)
        return

    insights = build_report_insights(report_rows)
    total_revenue = sum(row["revenue"] for row in report_rows)
    total_sold = sum(row["tickets_sold"] for row in report_rows)
    total_checked_in = sum(row["checked_in"] for row in report_rows)

    top1, top2, top3 = st.columns(3)
    top1.metric("Revenue", format_money(total_revenue))
    top2.metric("Tickets sold", total_sold)
    top3.metric("Checked in", total_checked_in)

    if insights["top_revenue"]:
        st.info(
            f"Top revenue event: {insights['top_revenue']['event'].title} with {format_money(insights['top_revenue']['revenue'])}."
        )
    if insights["top_attendance"]:
        st.info(
            f"Best attendance rate: {insights['top_attendance']['event'].title} at {insights['top_attendance']['attendance_rate']}%."
        )

    st.markdown("#### Event report table")
    for row in report_rows:
        st.markdown(
            f"""
            <div class="surface-card">
              <h4>{h(row["event"].title)}</h4>
              <p class="muted">{h(format_datetime(row["event"].event_date))} | {h(row["event"].venue)}, {h(row["event"].city)}</p>
              <p><strong>Sold:</strong> {row['tickets_sold']} | <strong>Checked in:</strong> {row['checked_in']} | <strong>Revenue:</strong> {format_money(row['revenue'])}</p>
              <p><strong>Fill rate:</strong> {row['fill_rate']}% | <strong>Attendance rate:</strong> {row['attendance_rate']}%</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_organizer_workspace(db: Session, user: User | None) -> None:
    render_hero(
        "Organizer workspace",
        "Create and manage events, review recent ticket activity, validate QR passes, and generate attendance reports from the same dashboard.",
    )
    if user is None or user.role not in {"organizer", "admin"}:
        st.warning("Organizer access is required for this page.")
        return

    organizer_scope_id = None if user.role == "admin" else user.id
    events = get_visible_events(db, organizer_scope_id)
    sold_map = get_sold_ticket_map(db)
    checked_map = get_checked_in_ticket_map(db)
    prepared_events = [prepare_event_card(event, sold_map.get(event.id, 0), checked_map.get(event.id, 0)) for event in events]
    recent_tickets = get_recent_tickets_for_scope(db, organizer_scope_id)
    stats = build_system_stats(db, organizer_scope_id)
    render_metrics(stats)

    overview_tab, create_tab, edit_tab, checkin_tab, reports_tab = st.tabs(
        ["Overview", "Create event", "Edit events", "Check-in", "Reports"]
    )

    with overview_tab:
        attention_events = build_attention_events(prepared_events)
        if attention_events:
            st.markdown("#### Events that need your attention")
            for event in attention_events:
                st.markdown(
                    f"""
                    <div class="surface-card">
                      <h4>{h(event.title)}</h4>
                      <p class="muted">{h(event.status_label)} | {h(format_datetime(event.event_date))} | {h(event.venue)}, {h(event.city)}</p>
                      <p><strong>Sold:</strong> {event.sold_tickets} | <strong>Pending arrivals:</strong> {event.pending_arrivals} | <strong>Fill rate:</strong> {event.fill_rate}%</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if prepared_events:
            st.markdown("#### Managed events")
            for event in prepared_events:
                render_event_card(event, user)
                st.write("")
        else:
            st.markdown('<div class="empty-state">You have not created any events yet.</div>', unsafe_allow_html=True)

        st.markdown("#### Recent bookings")
        if not recent_tickets:
            st.caption("No bookings yet.")
        for ticket in recent_tickets:
            st.markdown(
                f"""
                <div class="surface-card">
                  <strong>{h(ticket.ticket_code)}</strong> | {h(ticket.event.title)}<br>
                  <span class="muted">{h(ticket.purchaser_name)} booked {ticket.quantity} ticket(s)</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with create_tab:
        st.markdown("#### Publish a new event")
        render_event_editor(db, user)

    with edit_tab:
        st.markdown("#### Update or delete an event")
        if not prepared_events:
            st.caption("Create an event first.")
        else:
            event_options = [event.id for event in prepared_events]
            if st.session_state.selected_event_id not in event_options:
                st.session_state.selected_event_id = event_options[0]

            selected_id = st.selectbox(
                "Choose event",
                event_options,
                format_func=lambda event_id: next(
                    f"{event.title} | {format_datetime(event.event_date)}"
                    for event in prepared_events
                    if event.id == event_id
                ),
                key="selected_event_id",
            )
            selected_event = next(event for event in prepared_events if event.id == selected_id)
            render_event_editor(db, user, selected_event)

            st.markdown("#### Danger zone")
            confirm_delete = st.checkbox(
                "I understand that deleting this event also removes its tickets.",
                key=f"confirm-delete-{selected_event.id}",
            )
            if st.button(
                "Delete event",
                key=f"delete-event-{selected_event.id}",
                use_container_width=True,
                disabled=not confirm_delete,
            ):
                deleted_title = selected_event.title
                db.delete(selected_event)
                db.commit()
                st.session_state.selected_event_id = None
                add_notice("success", f"{deleted_title} was deleted successfully.")
                st.rerun()

    with checkin_tab:
        st.markdown("#### QR ticket validation")
        render_check_in_panel(db, user)

    with reports_tab:
        st.markdown("#### Sales and attendance reports")
        render_reports_panel(db, user)


def render_admin_console(db: Session, user: User | None) -> None:
    render_hero(
        "Admin console",
        "Manage platform users, review activity across all events, and keep the free Streamlit deployment ready for demo use.",
    )
    if user is None or user.role != "admin":
        st.warning("Admin access is required for this page.")
        return

    stats = build_system_stats(db)
    render_metrics(stats)

    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    event_counts = {
        user_id: count
        for user_id, count in db.execute(select(Event.organizer_id, func.count(Event.id)).group_by(Event.organizer_id)).all()
        if user_id is not None
    }
    ticket_counts = {
        user_id: quantity
        for user_id, quantity in db.execute(
            select(Ticket.purchaser_id, func.coalesce(func.sum(Ticket.quantity), 0)).group_by(Ticket.purchaser_id)
        ).all()
        if user_id is not None
    }

    st.markdown("#### User overview")
    for item in users:
        st.markdown(
            f"""
            <div class="surface-card">
              <strong>{h(item.full_name)}</strong> ({h(item.email)})<br>
              <span class="muted">Role: {h(ROLE_LABELS.get(item.role, item.role.title()))} | Status: {'Active' if item.is_active else 'Inactive'} | Events: {int(event_counts.get(item.id, 0))} | Tickets: {int(ticket_counts.get(item.id, 0))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not users:
        return

    selected_admin_user_id = st.selectbox(
        "Manage user",
        [item.id for item in users],
        format_func=lambda user_id: next(
            f"{item.full_name} | {item.email}" for item in users if item.id == user_id
        ),
        key="selected_admin_user_id",
    )
    target = next(item for item in users if item.id == selected_admin_user_id)

    st.markdown("#### Update role")
    new_role = st.selectbox(
        "Role",
        list(ROLE_LABELS.keys()),
        index=list(ROLE_LABELS.keys()).index(target.role),
        format_func=lambda role: ROLE_LABELS[role],
        key=f"role-for-{target.id}",
    )
    if st.button("Save role", key=f"save-role-{target.id}", use_container_width=True):
        if target.role == "admin" and new_role != "admin" and count_active_admins(db) <= 1:
            st.error("At least one active admin account must remain.")
        else:
            target.role = new_role
            db.add(target)
            db.commit()
            add_notice("success", f"{target.full_name} is now assigned as {ROLE_LABELS[new_role]}.")
            st.rerun()

    st.markdown("#### Account status")
    status_label = "Deactivate account" if target.is_active else "Reactivate account"
    if st.button(status_label, key=f"toggle-status-{target.id}", use_container_width=True):
        if target.id == user.id:
            st.error("You cannot deactivate your own account.")
        elif target.role == "admin" and target.is_active and count_active_admins(db) <= 1:
            st.error("At least one active admin account must remain.")
        else:
            target.is_active = not target.is_active
            db.add(target)
            db.commit()
            add_notice("success", f"{target.full_name} is now {'active' if target.is_active else 'inactive'}.")
            st.rerun()

    recent_tickets = db.scalars(
        select(Ticket)
        .options(selectinload(Ticket.event), selectinload(Ticket.purchaser))
        .order_by(Ticket.created_at.desc())
        .limit(8)
    ).all()
    st.markdown("#### Recent ticket activity")
    for ticket in recent_tickets:
        st.markdown(
            f"""
            <div class="surface-card">
              <strong>{h(ticket.ticket_code)}</strong> | {h(ticket.event.title)}<br>
              <span class="muted">{h(ticket.purchaser_name)} | {ticket.quantity} ticket(s) | {format_money(ticket.total_amount)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    init_state()
    render_app_style()

    with db_session() as db:
        user = current_user(db)
        render_sidebar(user)
        show_notices()

        page = st.session_state.nav_page
        if page == "Discover events":
            render_discover_page(db, user)
        elif page == "Sign in":
            render_sign_in_page(db, user)
        elif page == "Create account":
            render_create_account_page(db, user)
        elif page == "My tickets":
            render_my_tickets_page(db, user)
        elif page == "Organizer workspace":
            render_organizer_workspace(db, user)
        elif page == "Admin console":
            render_admin_console(db, user)


if __name__ == "__main__":
    main()
