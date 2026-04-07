from __future__ import annotations

import base64
import io
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import qrcode
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from qrcode.image.svg import SvgPathImage
from sqlalchemy import case, func, inspect, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, build_engine, build_session_factory
from .models import Event, Ticket, User
from .security import hash_password, normalize_email, verify_password
from .seed import seed_default_users


BASE_PATH = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

ROLE_LABELS = {
    "admin": "Admin",
    "organizer": "Organizer",
    "user": "User",
}


def get_db(request: Request):
    session = request.app.state.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_app(database_url: str | None = None) -> FastAPI:
    resolved_database_url = database_url or settings.database_url
    engine = build_engine(resolved_database_url)
    SessionLocal = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=engine)
        migrate_existing_schema(engine)
        with SessionLocal() as session:
            seed_default_users(session)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount("/static", StaticFiles(directory=str(BASE_PATH / "static")), name="static")
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    app.state.settings = settings

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        query = request.query_params.get("q", "").strip()

        stmt = select(Event).order_by(Event.event_date.asc())
        if query:
            search = f"%{query}%"
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
        checked_in_map = get_checked_in_ticket_map(db)
        current_user = resolve_current_user(request, db)
        prepared_events = [
            prepare_event_card(event, sold_map.get(event.id, 0), checked_in_map.get(event.id, 0)) for event in events
        ]
        for event in prepared_events:
            event.can_manage = bool(current_user and can_manage_event(current_user, event))
        stats = build_system_stats(db)
        featured_event = next((event for event in prepared_events if event.status_label == "Upcoming"), None)
        if featured_event is None and prepared_events:
            featured_event = prepared_events[0]

        return render_template(
            request,
            "index.html",
            {
                "page_title": "Discover events",
                "events": prepared_events,
                "query": query,
                "stats": stats,
                "timezone_label": settings.timezone_label,
                "featured_event": featured_event,
                "category_highlights": build_category_highlights(prepared_events),
                "current_user": current_user,
            },
        )

    @app.get("/dashboard")
    def dashboard_redirect(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
        auth_result = require_authenticated_user(request, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result
        return redirect_response(resolve_dashboard_path(auth_result))

    @app.get("/auth/register", response_class=HTMLResponse)
    def register_form(request: Request, db: Session = Depends(get_db)) -> Any:
        current_user = resolve_current_user(request, db)
        if current_user:
            return redirect_response(resolve_dashboard_path(current_user))
        next_url = request.query_params.get("next", "")
        return render_template(
            request,
            "register.html",
            {
                "page_title": "Create account",
                "errors": [],
                "form_data": {"full_name": "", "email": "", "role": "user"},
                "next_url": next_url,
                "current_user": current_user,
            },
        )

    @app.post("/auth/register", response_class=HTMLResponse)
    async def register(request: Request, db: Session = Depends(get_db)) -> Any:
        current_user = resolve_current_user(request, db)
        if current_user:
            return redirect_response(resolve_dashboard_path(current_user))

        form = await request.form()
        full_name = str(form.get("full_name", "")).strip()
        email = normalize_email(str(form.get("email", "")))
        password = str(form.get("password", ""))
        confirm_password = str(form.get("confirm_password", ""))
        role = str(form.get("role", "user")).strip()
        next_url = str(form.get("next", "")).strip()

        errors: list[str] = []
        if not full_name:
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
            return render_template(
                request,
                "register.html",
                {
                    "page_title": "Create account",
                    "errors": errors,
                    "form_data": {"full_name": full_name, "email": email, "role": role},
                    "next_url": next_url,
                    "current_user": current_user,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role="admin" if email in settings.admin_emails else role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        request.session["user_id"] = user.id
        flash(request, "success", f"Welcome to EventSphere, {user.full_name}.")
        return redirect_response(next_url or resolve_dashboard_path(user))

    @app.get("/auth/login", response_class=HTMLResponse)
    def login_form(request: Request, db: Session = Depends(get_db)) -> Any:
        current_user = resolve_current_user(request, db)
        if current_user:
            return redirect_response(resolve_dashboard_path(current_user))
        next_url = request.query_params.get("next", "")
        return render_template(
            request,
            "login.html",
            {
                "page_title": "Sign in",
                "errors": [],
                "form_data": {"email": ""},
                "next_url": next_url,
                "current_user": current_user,
            },
        )

    @app.post("/auth/login", response_class=HTMLResponse)
    async def login(request: Request, db: Session = Depends(get_db)) -> Any:
        current_user = resolve_current_user(request, db)
        if current_user:
            return redirect_response(resolve_dashboard_path(current_user))

        form = await request.form()
        email = normalize_email(str(form.get("email", "")))
        password = str(form.get("password", ""))
        next_url = str(form.get("next", "")).strip()

        user = db.scalar(select(User).where(User.email == email))
        errors: list[str] = []
        if user is None or not verify_password(password, user.password_hash):
            errors.append("Invalid email or password.")
        elif not user.is_active:
            errors.append("This account is currently inactive.")

        if errors:
            return render_template(
                request,
                "login.html",
                {
                    "page_title": "Sign in",
                    "errors": errors,
                    "form_data": {"email": email},
                    "next_url": next_url,
                    "current_user": current_user,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        request.session.clear()
        request.session["user_id"] = user.id
        flash(request, "success", f"Welcome back, {user.full_name}.")
        return redirect_response(next_url or resolve_dashboard_path(user))

    @app.post("/auth/logout")
    def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        flash(request, "success", "You have been signed out.")
        return redirect_response("/")

    @app.get("/my-tickets", response_class=HTMLResponse)
    def my_tickets(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_authenticated_user(request, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        tickets = db.scalars(
            select(Ticket)
            .options(selectinload(Ticket.event))
            .where(Ticket.purchaser_id == auth_result.id)
            .order_by(Ticket.created_at.desc())
        ).all()
        sold_map = get_sold_ticket_map(db)
        checked_in_map = get_checked_in_ticket_map(db)
        for ticket in tickets:
            prepare_event_card(ticket.event, sold_map.get(ticket.event.id, 0), checked_in_map.get(ticket.event.id, 0))

        return render_template(
            request,
            "my_tickets.html",
            {
                "page_title": "My tickets",
                "tickets": tickets,
                "current_user": auth_result,
            },
        )

    @app.get("/admin", response_class=HTMLResponse)
    def admin_dashboard(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        users = db.scalars(select(User).order_by(User.created_at.asc())).all()
        event_counts = {
            user_id: count
            for user_id, count in db.execute(
                select(Event.organizer_id, func.count(Event.id)).group_by(Event.organizer_id)
            ).all()
            if user_id is not None
        }
        ticket_counts = {
            user_id: quantity
            for user_id, quantity in db.execute(
                select(Ticket.purchaser_id, func.coalesce(func.sum(Ticket.quantity), 0))
                .where(Ticket.purchaser_id.is_not(None))
                .group_by(Ticket.purchaser_id)
            ).all()
            if user_id is not None
        }
        user_rows = [
            {
                "user": user,
                "event_count": int(event_counts.get(user.id, 0)),
                "ticket_count": int(ticket_counts.get(user.id, 0)),
            }
            for user in users
        ]
        recent_tickets = db.scalars(
            select(Ticket)
            .options(selectinload(Ticket.event), selectinload(Ticket.purchaser))
            .order_by(Ticket.created_at.desc())
            .limit(8)
        ).all()

        return render_template(
            request,
            "admin_dashboard.html",
            {
                "page_title": "Admin dashboard",
                "stats": build_system_stats(db),
                "user_rows": user_rows,
                "recent_tickets": recent_tickets,
                "admin_count": count_active_admins(db),
                "current_user": auth_result,
            },
        )

    @app.post("/admin/users/{user_id}/role")
    async def update_user_role(user_id: int, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
        auth_result = require_user_with_roles(request, {"admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        target = db.get(User, user_id)
        if target is None:
            flash(request, "danger", "User not found.")
            return redirect_response("/admin")

        form = await request.form()
        role = str(form.get("role", "")).strip()
        if role not in ROLE_LABELS:
            flash(request, "danger", "Select a valid role.")
            return redirect_response("/admin")

        if target.role == "admin" and role != "admin" and count_active_admins(db) <= 1:
            flash(request, "danger", "At least one active admin account must remain.")
            return redirect_response("/admin")

        target.role = role
        db.add(target)
        db.commit()
        flash(request, "success", f"{target.full_name} is now assigned as {ROLE_LABELS[role]}.")
        return redirect_response("/admin")

    @app.post("/admin/users/{user_id}/status")
    def update_user_status(user_id: int, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
        auth_result = require_user_with_roles(request, {"admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        target = db.get(User, user_id)
        if target is None:
            flash(request, "danger", "User not found.")
            return redirect_response("/admin")

        if target.id == auth_result.id:
            flash(request, "danger", "You cannot deactivate your own account.")
            return redirect_response("/admin")

        if target.role == "admin" and target.is_active and count_active_admins(db) <= 1:
            flash(request, "danger", "At least one active admin account must remain.")
            return redirect_response("/admin")

        target.is_active = not target.is_active
        db.add(target)
        db.commit()
        status_label = "active" if target.is_active else "inactive"
        flash(request, "success", f"{target.full_name} is now {status_label}.")
        return redirect_response("/admin")

    @app.get("/organizer", response_class=HTMLResponse)
    def organizer_dashboard(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        organizer_scope_id = None if auth_result.role == "admin" else auth_result.id
        events = get_visible_events(db, organizer_scope_id)
        sold_map = get_sold_ticket_map(db)
        checked_in_map = get_checked_in_ticket_map(db)
        prepared_events = [
            prepare_event_card(event, sold_map.get(event.id, 0), checked_in_map.get(event.id, 0)) for event in events
        ]
        recent_tickets = get_recent_tickets_for_scope(db, organizer_scope_id)

        return render_template(
            request,
            "organizer_dashboard.html",
            {
                "page_title": "Organizer dashboard",
                "events": prepared_events,
                "recent_tickets": recent_tickets,
                "stats": build_system_stats(db, organizer_scope_id),
                "attention_events": build_attention_events(prepared_events),
                "top_event": max(prepared_events, key=lambda event: event.sold_tickets, default=None),
                "current_user": auth_result,
            },
        )

    @app.get("/organizer/events/new", response_class=HTMLResponse)
    def new_event_form(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result
        return render_template(
            request,
            "event_form.html",
            {
                "page_title": "Create event",
                "event": None,
                "errors": [],
                "form_data": default_event_form_data(auth_result),
                "mode": "create",
                "current_user": auth_result,
            },
        )

    @app.post("/organizer/events/new", response_class=HTMLResponse)
    async def create_event(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        form = await request.form()
        form_data, errors = validate_event_form(form)
        if errors:
            return render_template(
                request,
                "event_form.html",
                {
                    "page_title": "Create event",
                    "event": None,
                    "errors": errors,
                    "form_data": {**default_event_form_data(auth_result), **form_data},
                    "mode": "create",
                    "current_user": auth_result,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        event = Event(
            organizer_id=auth_result.id,
            **form_data,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        flash(request, "success", "Event created successfully.")
        return redirect_response(f"/events/{event.id}")

    @app.get("/organizer/events/{event_id}/edit", response_class=HTMLResponse)
    def edit_event_form(event_id: int, request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        event = get_event_or_404(db, event_id)
        if not can_manage_event(auth_result, event):
            flash(request, "danger", "You do not have permission to manage this event.")
            return redirect_response("/organizer")

        return render_template(
            request,
            "event_form.html",
            {
                "page_title": f"Edit {event.title}",
                "event": event,
                "errors": [],
                "form_data": event_to_form_data(event),
                "mode": "edit",
                "current_user": auth_result,
            },
        )

    @app.post("/organizer/events/{event_id}/edit", response_class=HTMLResponse)
    async def update_event(event_id: int, request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        event = get_event_or_404(db, event_id)
        if not can_manage_event(auth_result, event):
            flash(request, "danger", "You do not have permission to manage this event.")
            return redirect_response("/organizer")

        form = await request.form()
        form_data, errors = validate_event_form(form)
        sold_tickets = get_sold_quantity_for_event(db, event.id)
        if not errors and form_data["capacity"] < sold_tickets:
            errors.append(f"Capacity cannot be lower than the {sold_tickets} tickets already sold.")
        if errors:
            return render_template(
                request,
                "event_form.html",
                {
                    "page_title": f"Edit {event.title}",
                    "event": event,
                    "errors": errors,
                    "form_data": form_data,
                    "mode": "edit",
                    "current_user": auth_result,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        for key, value in form_data.items():
            setattr(event, key, value)

        db.add(event)
        db.commit()
        flash(request, "success", "Event updated successfully.")
        return redirect_response(f"/events/{event.id}")

    @app.post("/organizer/events/{event_id}/delete")
    def delete_event(event_id: int, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        event = get_event_or_404(db, event_id)
        if not can_manage_event(auth_result, event):
            flash(request, "danger", "You do not have permission to delete this event.")
            return redirect_response("/organizer")

        db.delete(event)
        db.commit()
        flash(request, "success", "Event deleted successfully.")
        return redirect_response("/organizer")

    @app.get("/events/{event_id}", response_class=HTMLResponse)
    def event_detail(event_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        event = get_event_or_404(db, event_id)
        sold_tickets = get_sold_quantity_for_event(db, event.id)
        checked_in = get_checked_in_quantity_for_event(db, event.id)
        prepared_event = prepare_event_card(event, sold_tickets, checked_in)
        current_user = resolve_current_user(request, db)

        return render_template(
            request,
            "event_detail.html",
            {
                "page_title": event.title,
                "event": prepared_event,
                "booking_errors": [],
                "booking_form": default_booking_form_data(current_user),
                "recommended_events": build_recommended_events(db, event.id, event.category),
                "can_manage_event": bool(current_user and can_manage_event(current_user, event)),
            },
        )

    @app.post("/events/{event_id}/book", response_class=HTMLResponse)
    async def book_ticket(event_id: int, request: Request, db: Session = Depends(get_db)) -> Any:
        current_user = resolve_current_user(request, db)
        if current_user is None:
            flash(request, "warning", "Sign in to complete a booking.")
            return redirect_response(f"/auth/login?next={quote(f'/events/{event_id}')}")

        event = get_event_or_404(db, event_id)
        sold_tickets = get_sold_quantity_for_event(db, event.id)
        checked_in = get_checked_in_quantity_for_event(db, event.id)
        prepared_event = prepare_event_card(event, sold_tickets, checked_in)

        form = await request.form()
        booking_form, errors = validate_booking_form(form, current_user)
        if not is_booking_open(prepared_event):
            errors.append("Bookings are closed for this event.")
        if booking_form["quantity"] > prepared_event.remaining_capacity:
            errors.append("Requested ticket quantity exceeds remaining capacity.")

        if errors:
            return render_template(
                request,
                "event_detail.html",
                {
                    "page_title": event.title,
                    "event": prepared_event,
                    "booking_errors": errors,
                    "booking_form": booking_form,
                    "recommended_events": build_recommended_events(db, event.id, event.category),
                    "can_manage_event": can_manage_event(current_user, event),
                    "current_user": current_user,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ticket = Ticket(
            event_id=event.id,
            purchaser_id=current_user.id,
            purchaser_name=current_user.full_name,
            purchaser_email=current_user.email,
            quantity=booking_form["quantity"],
            total_amount=event.ticket_price * booking_form["quantity"],
            payment_method=booking_form["payment_method"],
            payment_status="Confirmed",
            ticket_code=generate_ticket_code(db),
        )
        db.add(ticket)
        db.commit()

        flash(request, "success", "Booking confirmed. Your digital ticket is ready.")
        return redirect_response(f"/tickets/{ticket.ticket_code}")

    @app.get("/tickets/{ticket_code}", response_class=HTMLResponse)
    def ticket_detail(ticket_code: str, request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_authenticated_user(request, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        ticket = get_ticket_or_404(db, ticket_code)
        if not can_view_ticket(auth_result, ticket):
            flash(request, "danger", "You do not have permission to view this ticket.")
            return redirect_response("/my-tickets")

        validation_url = f"{request.url_for('check_in_page')}?code={ticket.ticket_code}"

        return render_template(
            request,
            "ticket_detail.html",
            {
                "page_title": f"Ticket {ticket.ticket_code}",
                "ticket": ticket,
                "validation_url": validation_url,
                "qr_svg_data_uri": generate_qr_svg_data_uri(validation_url),
                "can_validate_ticket": can_validate_ticket(auth_result, ticket),
                "current_user": auth_result,
            },
        )

    @app.get("/organizer/check-in", response_class=HTMLResponse)
    def check_in_page(request: Request, code: str | None = None, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        ticket = None
        message: tuple[str, str] | None = None
        if code:
            candidate = get_ticket_or_none(db, code.strip().upper())
            if candidate and can_validate_ticket(auth_result, candidate):
                ticket = candidate
            elif candidate:
                message = ("danger", "You do not have permission to validate this ticket.")
            else:
                message = ("danger", "Ticket not found.")

        organizer_scope_id = None if auth_result.role == "admin" else auth_result.id
        return render_template(
            request,
            "check_in.html",
            {
                "page_title": "Ticket validation",
                "ticket": ticket,
                "code": code or "",
                "message": message,
                "stats": build_system_stats(db, organizer_scope_id),
                "current_user": auth_result,
            },
        )

    @app.post("/organizer/check-in", response_class=HTMLResponse)
    async def perform_check_in(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        form = await request.form()
        code = str(form.get("code", "")).strip().upper()
        action = str(form.get("action", "lookup")).strip()
        ticket = get_ticket_or_none(db, code) if code else None
        message: tuple[str, str] | None = None

        if not code:
            message = ("danger", "Enter a valid ticket code.")
        elif ticket is None:
            message = ("danger", "Ticket not found.")
        elif not can_validate_ticket(auth_result, ticket):
            ticket = None
            message = ("danger", "You do not have permission to validate this ticket.")
        elif action == "confirm":
            if ticket.checked_in_at is not None:
                message = ("warning", "This ticket was already checked in earlier.")
            else:
                ticket.checked_in_at = datetime.now()
                db.add(ticket)
                db.commit()
                db.refresh(ticket)
                message = ("success", "Check-in completed successfully.")
        else:
            message = ("info", "Ticket loaded. Review the details and confirm check-in.")

        organizer_scope_id = None if auth_result.role == "admin" else auth_result.id
        return render_template(
            request,
            "check_in.html",
            {
                "page_title": "Ticket validation",
                "ticket": ticket,
                "code": code,
                "message": message,
                "stats": build_system_stats(db, organizer_scope_id),
                "current_user": auth_result,
            },
        )

    @app.get("/reports", response_class=HTMLResponse)
    def reports(request: Request, db: Session = Depends(get_db)) -> Any:
        auth_result = require_user_with_roles(request, {"organizer", "admin"}, db)
        if isinstance(auth_result, RedirectResponse):
            return auth_result

        organizer_scope_id = None if auth_result.role == "admin" else auth_result.id
        event_rows = db.execute(build_report_statement(organizer_scope_id)).all()

        report_rows = []
        for event, tickets_sold, checked_in, revenue in event_rows:
            tickets_sold = int(tickets_sold or 0)
            checked_in = int(checked_in or 0)
            revenue = float(revenue or 0.0)
            fill_rate = round((tickets_sold / event.capacity) * 100) if event.capacity else 0
            attendance_rate = round((checked_in / tickets_sold) * 100) if tickets_sold else 0
            report_rows.append(
                {
                    "event": prepare_event_card(event, tickets_sold, checked_in),
                    "tickets_sold": tickets_sold,
                    "checked_in": checked_in,
                    "revenue": revenue,
                    "fill_rate": fill_rate,
                    "attendance_rate": attendance_rate,
                }
            )

        return render_template(
            request,
            "reports.html",
            {
                "page_title": "Sales and attendance reports",
                "stats": build_system_stats(db, organizer_scope_id),
                "report_rows": report_rows,
                "report_insights": build_report_insights(report_rows),
                "current_user": auth_result,
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def migrate_existing_schema(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "events" in table_names:
            event_columns = {column["name"] for column in inspector.get_columns("events")}
            if "organizer_id" not in event_columns:
                connection.exec_driver_sql("ALTER TABLE events ADD COLUMN organizer_id INTEGER")

        if "tickets" in table_names:
            ticket_columns = {column["name"] for column in inspector.get_columns("tickets")}
            if "purchaser_id" not in ticket_columns:
                connection.exec_driver_sql("ALTER TABLE tickets ADD COLUMN purchaser_id INTEGER")


def render_template(
    request: Request,
    template_name: str,
    context: dict[str, Any],
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    current_user = context.get("current_user")
    if current_user is None:
        current_user = resolve_current_user(request)
    merged_context = {
        "current_user": current_user,
        "flash_messages": consume_flash_messages(request),
        "role_labels": ROLE_LABELS,
        **context,
    }
    return templates.TemplateResponse(request, template_name, merged_context, status_code=status_code)


def flash(request: Request, category: str, message: str) -> None:
    messages = request.session.setdefault("_flash_messages", [])
    messages.append({"category": category, "message": message})


def consume_flash_messages(request: Request) -> list[dict[str, str]]:
    return list(request.session.pop("_flash_messages", []))


def redirect_response(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def resolve_dashboard_path(user: User) -> str:
    if user.role == "admin":
        return "/admin"
    if user.role == "organizer":
        return "/organizer"
    return "/my-tickets"


def resolve_current_user(request: Request, db: Session | None = None) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    owns_session = db is None
    if db is None:
        db = request.app.state.SessionLocal()

    try:
        user = db.get(User, user_id)
        if user and user.is_active:
            return user
        request.session.pop("user_id", None)
        return None
    finally:
        if owns_session:
            db.close()


def require_authenticated_user(request: Request, db: Session | None = None) -> User | RedirectResponse:
    current_user = resolve_current_user(request, db)
    if current_user is None:
        flash(request, "warning", "Sign in to continue.")
        return redirect_response(f"/auth/login?next={quote(request.url.path)}")
    return current_user


def require_user_with_roles(request: Request, roles: set[str], db: Session | None = None) -> User | RedirectResponse:
    auth_result = require_authenticated_user(request, db)
    if isinstance(auth_result, RedirectResponse):
        return auth_result
    if auth_result.role not in roles:
        flash(request, "danger", "You do not have permission to access that page.")
        return redirect_response(resolve_dashboard_path(auth_result))
    return auth_result


def can_manage_event(user: User, event: Event) -> bool:
    return user.role == "admin" or event.organizer_id == user.id


def can_validate_ticket(user: User, ticket: Ticket) -> bool:
    return user.role == "admin" or ticket.event.organizer_id == user.id


def can_view_ticket(user: User, ticket: Ticket) -> bool:
    return user.role == "admin" or ticket.event.organizer_id == user.id or ticket.purchaser_id == user.id


def get_event_or_404(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def get_ticket_or_none(db: Session, ticket_code: str | None) -> Ticket | None:
    if not ticket_code:
        return None
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.event), selectinload(Ticket.purchaser))
        .where(Ticket.ticket_code == ticket_code)
    )
    return db.scalar(stmt)


def get_ticket_or_404(db: Session, ticket_code: str) -> Ticket:
    ticket = get_ticket_or_none(db, ticket_code)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def get_visible_events(db: Session, organizer_scope_id: int | None = None) -> list[Event]:
    stmt = select(Event).order_by(Event.event_date.asc())
    if organizer_scope_id is not None:
        stmt = stmt.where(Event.organizer_id == organizer_scope_id)
    return db.scalars(stmt).all()


def get_recent_tickets_for_scope(db: Session, organizer_scope_id: int | None = None) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.event), selectinload(Ticket.purchaser))
        .order_by(Ticket.created_at.desc())
        .limit(6)
    )
    if organizer_scope_id is not None:
        stmt = stmt.join(Event).where(Event.organizer_id == organizer_scope_id)
    return db.scalars(stmt).all()


def get_sold_ticket_map(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Ticket.event_id, func.coalesce(func.sum(Ticket.quantity), 0)).group_by(Ticket.event_id)
    ).all()
    return {event_id: int(quantity or 0) for event_id, quantity in rows}


def get_checked_in_ticket_map(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(
            Ticket.event_id,
            func.coalesce(
                func.sum(case((Ticket.checked_in_at.is_not(None), Ticket.quantity), else_=0)),
                0,
            ),
        ).group_by(Ticket.event_id)
    ).all()
    return {event_id: int(quantity or 0) for event_id, quantity in rows}


def get_sold_quantity_for_event(db: Session, event_id: int) -> int:
    value = db.scalar(select(func.coalesce(func.sum(Ticket.quantity), 0)).where(Ticket.event_id == event_id))
    return int(value or 0)


def get_checked_in_quantity_for_event(db: Session, event_id: int) -> int:
    value = db.scalar(
        select(func.coalesce(func.sum(case((Ticket.checked_in_at.is_not(None), Ticket.quantity), else_=0)), 0)).where(
            Ticket.event_id == event_id
        )
    )
    return int(value or 0)


def build_system_stats(db: Session, organizer_scope_id: int | None = None) -> dict[str, Any]:
    now = datetime.now()

    event_stmt = select(
        func.count(Event.id),
        func.coalesce(func.sum(Event.capacity), 0),
        func.count().filter(Event.event_date >= now),
        func.count().filter(Event.event_date <= now, Event.event_date >= now - timedelta(hours=6)),
    )
    if organizer_scope_id is not None:
        event_stmt = event_stmt.where(Event.organizer_id == organizer_scope_id)
    total_events, total_capacity, upcoming, running = db.execute(event_stmt).one()

    ticket_stmt = select(
        func.coalesce(func.sum(Ticket.quantity), 0),
        func.coalesce(func.sum(Ticket.total_amount), 0.0),
        func.coalesce(func.sum(case((Ticket.checked_in_at.is_not(None), Ticket.quantity), else_=0)), 0),
    ).select_from(Ticket).join(Event, Ticket.event_id == Event.id)
    if organizer_scope_id is not None:
        ticket_stmt = ticket_stmt.where(Event.organizer_id == organizer_scope_id)
    tickets_sold, revenue, checked_in = db.execute(ticket_stmt).one()

    total_events = int(total_events or 0)
    total_capacity = int(total_capacity or 0)
    tickets_sold = int(tickets_sold or 0)
    checked_in = int(checked_in or 0)
    revenue = float(revenue or 0.0)

    return {
        "total_events": total_events,
        "tickets_sold": tickets_sold,
        "checked_in": checked_in,
        "revenue": revenue,
        "upcoming_events": int(upcoming or 0),
        "running_events": int(running or 0),
        "total_capacity": total_capacity,
        "pending_arrivals": max(tickets_sold - checked_in, 0),
        "sell_through": round((tickets_sold / total_capacity) * 100) if total_capacity else 0,
    }


def build_report_statement(organizer_scope_id: int | None = None):
    stmt = (
        select(
            Event,
            func.coalesce(func.sum(Ticket.quantity), 0).label("tickets_sold"),
            func.coalesce(
                func.sum(
                    case(
                        (Ticket.checked_in_at.is_not(None), Ticket.quantity),
                        else_=0,
                    )
                ),
                0,
            ).label("checked_in"),
            func.coalesce(func.sum(Ticket.total_amount), 0.0).label("revenue"),
        )
        .outerjoin(Ticket, Ticket.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.event_date.asc())
    )
    if organizer_scope_id is not None:
        stmt = stmt.where(Event.organizer_id == organizer_scope_id)
    return stmt


def count_active_admins(db: Session) -> int:
    return int(db.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))) or 0)


def default_event_form_data(current_user: User | None = None) -> dict[str, Any]:
    organizer_name = current_user.full_name if current_user else ""
    return {
        "title": "",
        "category": "",
        "organizer_name": organizer_name,
        "venue": "",
        "city": "Almaty",
        "description": "",
        "event_date": "",
        "ticket_price": "",
        "capacity": "",
        "image_url": "",
    }


def event_to_form_data(event: Event) -> dict[str, Any]:
    return {
        "title": event.title,
        "category": event.category,
        "organizer_name": event.organizer_name,
        "venue": event.venue,
        "city": event.city,
        "description": event.description,
        "event_date": event.event_date.strftime("%Y-%m-%dT%H:%M"),
        "ticket_price": int(event.ticket_price) if event.ticket_price.is_integer() else event.ticket_price,
        "capacity": event.capacity,
        "image_url": event.image_url or "",
    }


def validate_event_form(form) -> tuple[dict[str, Any], list[str]]:
    form_data = {
        "title": str(form.get("title", "")).strip(),
        "category": str(form.get("category", "")).strip(),
        "organizer_name": str(form.get("organizer_name", "")).strip(),
        "venue": str(form.get("venue", "")).strip(),
        "city": str(form.get("city", "")).strip(),
        "description": str(form.get("description", "")).strip(),
        "event_date": str(form.get("event_date", "")).strip(),
        "ticket_price": str(form.get("ticket_price", "")).strip(),
        "capacity": str(form.get("capacity", "")).strip(),
        "image_url": str(form.get("image_url", "")).strip(),
    }
    errors = []

    required_fields = [
        ("title", "Title"),
        ("category", "Category"),
        ("organizer_name", "Organizer"),
        ("venue", "Venue"),
        ("city", "City"),
        ("description", "Description"),
        ("event_date", "Event date"),
        ("ticket_price", "Ticket price"),
        ("capacity", "Capacity"),
    ]
    for key, label in required_fields:
        if not form_data[key]:
            errors.append(f"{label} is required.")

    event_date = None
    ticket_price = 0.0
    capacity = 0

    if form_data["event_date"]:
        try:
            event_date = datetime.fromisoformat(form_data["event_date"])
            if event_date <= datetime.now():
                errors.append("Event date must be in the future.")
        except ValueError:
            errors.append("Event date has an invalid format.")

    if form_data["ticket_price"]:
        try:
            ticket_price = float(form_data["ticket_price"])
            if ticket_price <= 0:
                errors.append("Ticket price must be greater than zero.")
        except ValueError:
            errors.append("Ticket price must be numeric.")

    if form_data["capacity"]:
        try:
            capacity = int(form_data["capacity"])
            if capacity <= 0:
                errors.append("Capacity must be greater than zero.")
        except ValueError:
            errors.append("Capacity must be an integer.")

    if errors:
        return form_data, errors

    return (
        {
            "title": form_data["title"],
            "category": form_data["category"],
            "organizer_name": form_data["organizer_name"],
            "venue": form_data["venue"],
            "city": form_data["city"],
            "description": form_data["description"],
            "event_date": event_date,
            "ticket_price": ticket_price,
            "capacity": capacity,
            "image_url": form_data["image_url"] or None,
        },
        [],
    )


def default_booking_form_data(current_user: User | None = None) -> dict[str, Any]:
    return {
        "purchaser_name": current_user.full_name if current_user else "",
        "purchaser_email": current_user.email if current_user else "",
        "quantity": 1,
        "payment_method": "Kaspi Pay",
    }


def validate_booking_form(form, current_user: User) -> tuple[dict[str, Any], list[str]]:
    payment_method = str(form.get("payment_method", "")).strip()
    quantity_raw = str(form.get("quantity", "1")).strip()
    errors = []

    if not payment_method:
        errors.append("Select a payment method.")

    quantity = 1
    try:
        quantity = int(quantity_raw)
        if quantity <= 0 or quantity > 10:
            errors.append("Ticket quantity must be between 1 and 10.")
    except ValueError:
        errors.append("Ticket quantity must be an integer.")

    return {
        "purchaser_name": current_user.full_name,
        "purchaser_email": current_user.email,
        "quantity": quantity,
        "payment_method": payment_method,
    }, errors


def is_booking_open(event: Event) -> bool:
    return event.status_label == "Upcoming" and not event.is_sold_out


def prepare_event_card(event: Event, sold_tickets: int, checked_in: int) -> Event:
    now = datetime.now()
    if event.event_date < now - timedelta(hours=6):
        status_label = "Completed"
        status_variant = "status-completed"
    elif event.event_date <= now:
        status_label = "Live"
        status_variant = "status-live"
    else:
        status_label = "Upcoming"
        status_variant = "status-upcoming"

    remaining_capacity = max(event.capacity - sold_tickets, 0)
    fill_rate = round((sold_tickets / event.capacity) * 100) if event.capacity else 0
    attendance_rate = round((checked_in / sold_tickets) * 100) if sold_tickets else 0

    event.status_label = status_label
    event.status_variant = status_variant
    event.remaining_capacity = remaining_capacity
    event.sold_tickets = sold_tickets
    event.checked_in_tickets = checked_in
    event.fill_rate = fill_rate
    event.attendance_rate = attendance_rate
    event.is_sold_out = remaining_capacity <= 0
    event.is_bookable = is_booking_open(event)
    event.pending_arrivals = max(sold_tickets - checked_in, 0)
    return event


def build_category_highlights(events: list[Event]) -> list[dict[str, Any]]:
    counter = Counter(event.category for event in events)
    sold_counter = Counter()
    for event in events:
        sold_counter[event.category] += event.sold_tickets

    return [
        {"name": category, "count": count, "tickets_sold": sold_counter[category]}
        for category, count in counter.most_common(5)
    ]


def build_attention_events(events: list[Event]) -> list[Event]:
    ranked = [
        event
        for event in sorted(events, key=lambda item: (item.fill_rate, -item.remaining_capacity, item.sold_tickets), reverse=True)
        if event.status_label != "Completed"
    ]
    return ranked[:4]


def build_recommended_events(db: Session, current_event_id: int, category: str) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.id != current_event_id, Event.category == category)
        .order_by(Event.event_date.asc())
        .limit(3)
    )
    events = db.scalars(stmt).all()
    sold_map = get_sold_ticket_map(db)
    checked_in_map = get_checked_in_ticket_map(db)
    return [prepare_event_card(event, sold_map.get(event.id, 0), checked_in_map.get(event.id, 0)) for event in events]


def build_report_insights(report_rows: list[dict[str, Any]]) -> dict[str, Any]:
    top_revenue = max((row for row in report_rows if row["revenue"] > 0), key=lambda row: row["revenue"], default=None)
    top_attendance = max(
        (row for row in report_rows if row["checked_in"] > 0),
        key=lambda row: row["attendance_rate"],
        default=None,
    )
    average_fill = round(sum(row["fill_rate"] for row in report_rows) / len(report_rows)) if report_rows else 0

    return {
        "top_revenue": top_revenue,
        "top_attendance": top_attendance,
        "average_fill": average_fill,
    }


def format_money(value: float) -> str:
    return f"{value:,.0f} KZT".replace(",", " ")


def format_datetime(value: datetime) -> str:
    return value.strftime("%d %b %Y, %H:%M")


def generate_ticket_code(db: Session) -> str:
    while True:
        ticket_code = f"EVT-{secrets.token_hex(4).upper()}"
        if db.scalar(select(Ticket.id).where(Ticket.ticket_code == ticket_code)) is None:
            return ticket_code


def generate_qr_svg_data_uri(value: str) -> str:
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(value)
    qr.make(fit=True)

    stream = io.BytesIO()
    image = qr.make_image(image_factory=SvgPathImage)
    image.save(stream)
    encoded = base64.b64encode(stream.getvalue()).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


templates.env.filters["money"] = format_money
templates.env.filters["datetime"] = format_datetime
templates.env.globals["current_year"] = datetime.now().year
