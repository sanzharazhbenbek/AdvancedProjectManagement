from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "eventsphere.db"


def parse_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@dataclass(slots=True)
class Settings:
    app_name: str = "EventSphere"
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")
    timezone_label: str = os.getenv("TIMEZONE_LABEL", "Asia/Almaty")
    session_secret: str = os.getenv("SESSION_SECRET", "eventsphere-session-secret")
    public_app_url: str = os.getenv("PUBLIC_APP_URL", "https://eventsphere.streamlit.app").rstrip("/")
    admin_emails: tuple[str, ...] = parse_csv(os.getenv("ADMIN_EMAILS", ""))
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    reload: bool = os.getenv("APP_RELOAD", "").lower() in {"1", "true", "yes", "on"}


settings = Settings()
