from __future__ import annotations

import base64
import io
from pathlib import Path

from core.config import settings
from db.repositories import EmailLogRepository
from services.qr_service import generate_qr_image
from utils.formatters import format_datetime, format_kzt, seat_label


def create_ticket_delivery(session, ticket) -> dict[str, str | None]:
    settings.tickets_dir.mkdir(parents=True, exist_ok=True)
    attachment_path = _generate_ticket_document(ticket)
    ticket.ticket_file_path = attachment_path
    session.add(ticket)
    session.flush()

    email_logs = EmailLogRepository(session).list_for_ticket(ticket.id)
    if not email_logs:
        EmailLogRepository(session).create(
            recipient_email=ticket.user.email,
            subject=f"Your EventSphere ticket for {ticket.event.title}",
            body=_build_email_body(ticket),
            attachment_path=attachment_path,
            status="delivered",
            booking_id=ticket.booking_id,
            ticket_id=ticket.id,
            event_id=ticket.event_id,
            user_id=ticket.user_id,
        )

    return {"attachment_path": attachment_path}


def _build_email_body(ticket) -> str:
    return "\n".join(
        [
            f"Payment confirmed for {ticket.event.title}.",
            "",
            f"Event: {ticket.event.title}",
            f"Date and time: {format_datetime(ticket.event.event_datetime)}",
            f"Venue: {ticket.event.venue}, {ticket.event.city}",
            f"Seat: {seat_label(ticket.category, ticket.row_label, ticket.seat_number)}",
            f"Ticket code: {ticket.ticket_code}",
            f"Price: {format_kzt(ticket.price_kzt or ticket.booking.amount_kzt)}",
            f"Ticket link: {ticket.qr_payload}",
        ]
    )


def _generate_ticket_document(ticket) -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception:
        return _generate_html_ticket(ticket)

    file_path = settings.tickets_dir / f"{ticket.ticket_code}.pdf"
    qr_bytes = generate_qr_image(ticket.qr_payload)
    qr_image = ImageReader(io.BytesIO(qr_bytes))

    pdf = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    pdf.setTitle(f"EventSphere Ticket {ticket.ticket_code}")

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(40, height - 60, "EventSphere")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(40, height - 82, "Paid digital ticket")

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, height - 130, ticket.event.title)

    lines = [
        f"Date and time: {format_datetime(ticket.event.event_datetime)}",
        f"Venue: {ticket.event.venue}, {ticket.event.city}",
        f"Attendee: {ticket.user.full_name} ({ticket.user.email})",
        f"Seat: {seat_label(ticket.category, ticket.row_label, ticket.seat_number)}",
        f"Price: {format_kzt(ticket.price_kzt or ticket.booking.amount_kzt)}",
        f"Ticket code: {ticket.ticket_code}",
        "Payment status: Paid",
    ]
    y = height - 170
    pdf.setFont("Helvetica", 12)
    for line in lines:
        pdf.drawString(40, y, line)
        y -= 22

    pdf.drawImage(qr_image, width - 210, height - 310, width=150, height=150, mask="auto")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(width - 210, height - 325, "Scan for check-in")
    pdf.drawString(40, 50, "Issued by EventSphere.")
    pdf.save()
    return str(file_path)


def _generate_html_ticket(ticket) -> str:
    file_path = settings.tickets_dir / f"{ticket.ticket_code}.html"
    qr_bytes = generate_qr_image(ticket.qr_payload)
    qr_base64 = base64.b64encode(qr_bytes).decode("ascii")
    html = f"""
    <html>
      <head><title>EventSphere Ticket {ticket.ticket_code}</title></head>
      <body style="font-family: Arial, sans-serif; padding: 24px;">
        <h1>EventSphere</h1>
        <h2>{ticket.event.title}</h2>
        <p><strong>Date and time:</strong> {format_datetime(ticket.event.event_datetime)}</p>
        <p><strong>Venue:</strong> {ticket.event.venue}, {ticket.event.city}</p>
        <p><strong>Attendee:</strong> {ticket.user.full_name} ({ticket.user.email})</p>
        <p><strong>Seat:</strong> {seat_label(ticket.category, ticket.row_label, ticket.seat_number)}</p>
        <p><strong>Price:</strong> {format_kzt(ticket.price_kzt or ticket.booking.amount_kzt)}</p>
        <p><strong>Ticket code:</strong> {ticket.ticket_code}</p>
        <p><strong>Payment status:</strong> Paid</p>
        <p><strong>Check-in QR:</strong></p>
        <img src="data:image/png;base64,{qr_base64}" alt="QR code" />
      </body>
    </html>
    """
    file_path.write_text(html, encoding="utf-8")
    return str(file_path)
