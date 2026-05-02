from __future__ import annotations

import io
from urllib.parse import parse_qs, urlparse

import qrcode

from core.config import settings


def build_payment_payload(booking_id: int, payment_reference: str | None = None) -> str:
    suffix = f"&reference={payment_reference}" if payment_reference else ""
    return f"{settings.public_app_url}?route=payment&booking_id={booking_id}{suffix}"


def build_ticket_payload(ticket_id: int, ticket_code: str) -> str:
    return f"{settings.public_app_url}?route=ticket&ticket_id={ticket_id}&code={ticket_code}"


def generate_qr_image(payload: str) -> bytes:
    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def parse_ticket_lookup(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("ES-"):
        return raw
    parsed = urlparse(raw)
    params = parse_qs(parsed.query)
    code = params.get("code", [None])[0]
    if code:
        return code
    if parsed.path:
        tail = parsed.path.strip("/").split("/")[-1]
        if tail.startswith("ES-"):
            return tail
    return None
