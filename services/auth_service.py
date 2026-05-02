from __future__ import annotations

from typing import Any

from core.security import hash_password, normalize_email, verify_password
from core.session import clear_user, flash, get_user_id, set_user_id
from db.database import session_scope
from db.repositories import UserRepository
from utils.formatters import role_label


def serialize_user(user) -> dict[str, Any]:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "role_label": role_label(user.role),
        "is_active": bool(user.is_active),
        "created_at": user.created_at,
    }


def get_current_user() -> dict[str, Any] | None:
    user_id = get_user_id()
    if user_id is None:
        return None

    with session_scope() as session:
        user = UserRepository(session).get_by_id(user_id)
        if user is None or not user.is_active:
            clear_user()
            return None
        return serialize_user(user)


def sign_in(email: str, password: str) -> tuple[dict[str, Any] | None, list[str]]:
    normalized_email = normalize_email(email)
    with session_scope() as session:
        user = UserRepository(session).get_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            return None, ["Invalid email or password."]
        if not user.is_active:
            return None, ["This account has been deactivated. Contact an administrator."]
        set_user_id(user.id)
        flash("success", f"Welcome back, {user.full_name.split()[0]}.")
        return serialize_user(user), []


def register_user(full_name: str, email: str, password: str, role: str) -> tuple[dict[str, Any] | None, list[str]]:
    normalized_email = normalize_email(email)
    with session_scope() as session:
        users = UserRepository(session)
        if users.get_by_email(normalized_email) is not None:
            return None, ["An account with this email already exists."]

        user = users.create(
            full_name=full_name.strip(),
            email=normalized_email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        set_user_id(user.id)
        flash("success", "Your EventSphere account is ready.")
        return serialize_user(user), []


def sign_out() -> None:
    clear_user()
    flash("success", "You have been signed out.")
