from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "EventSphere"
    brand_name: str = "EventSphere"
    timezone_name: str = "Asia/Almaty"
    currency_code: str = "KZT"
    payment_provider: str = "kaspi_sandbox"
    payment_window_minutes: int = int(os.getenv("PAYMENT_WINDOW_MINUTES", "15"))
    session_user_key: str = "eventsphere_user_id"
    session_redirect_key: str = "eventsphere_redirect_target"
    session_flash_key: str = "eventsphere_flash_messages"
    session_selected_event_key: str = "eventsphere_selected_event"
    session_selected_booking_key: str = "eventsphere_selected_booking"
    session_selected_ticket_key: str = "eventsphere_selected_ticket"

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def assets_dir(self) -> Path:
        return self.base_dir / "assets"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "eventsphere.db"

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", f"sqlite:///{self.database_path}")

    @property
    def public_app_url(self) -> str:
        return os.getenv("PUBLIC_APP_URL", "http://localhost:8501").rstrip("/")


settings = Settings()
