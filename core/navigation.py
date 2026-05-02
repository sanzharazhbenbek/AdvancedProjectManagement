from __future__ import annotations


ROUTE_TO_PAGE = {
    "discover": "pages/discover.py",
    "event_detail": "pages/event_detail.py",
    "sign_in": "pages/sign_in.py",
    "create_account": "pages/create_account.py",
    "user_dashboard": "pages/user_dashboard.py",
    "organizer_dashboard": "pages/organizer_dashboard.py",
    "create_event": "pages/create_event.py",
    "my_events": "pages/my_events.py",
    "organizer_reports": "pages/organizer_reports.py",
    "admin_dashboard": "pages/admin_dashboard.py",
    "manage_users": "pages/manage_users.py",
    "manage_events": "pages/manage_events.py",
    "admin_reports": "pages/admin_reports.py",
    "payment": "pages/payment_simulator.py",
    "ticket": "pages/ticket_view.py",
    "check_in": "pages/check_in.py",
}

ROLE_HOME_ROUTES = {
    "user": "discover",
    "organizer": "organizer_dashboard",
    "admin": "admin_dashboard",
}


def page_for_route(route: str | None) -> str:
    return ROUTE_TO_PAGE.get(route or "discover", ROUTE_TO_PAGE["discover"])


def default_route_for_role(role: str | None) -> str:
    return ROLE_HOME_ROUTES.get(role or "user", "discover")
