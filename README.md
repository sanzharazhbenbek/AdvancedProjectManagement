# EventSphere

EventSphere is a Streamlit-based event and ticketing management platform built to feel closer to a production-style SaaS workflow than a classroom MVP. It supports event discovery, persistent seat inventory, role-based authentication, organizer operations, simulated Kaspi-style QR payments, digital tickets, email delivery logs, and QR/manual attendance check-in.

## What’s Included

- public event discovery with search, filters, sorting, and featured content
- role-based sign in, account creation, and session-aware navigation
- secure password hashing with PBKDF2
- SQLite persistence through SQLAlchemy
- persistent per-event seat maps with category, row, seat number, and status tracking
- pending booking flow with expiring seat reservations and token-based QR payment confirmation
- QR ticket generation and per-ticket validation
- ticket delivery simulation with saved email logs and downloadable ticket files
- organizer dashboards with KPIs, event management, attendee lists, and reports
- admin dashboards with user/event management, operational tables, exports, and platform reporting
- first-run seeding with realistic Kazakhstan event data

## Project Structure

```text
.
├── app.py
├── streamlit_app.py
├── requirements.txt
├── README.md
├── .streamlit/
│   └── config.toml
├── assets/
│   └── images/
├── components/
├── core/
├── data/
├── db/
├── pages/
├── services/
└── utils/
```

## Tech Stack

- Python
- Streamlit
- SQLAlchemy
- SQLite
- Pandas
- QRCode / Pillow
- ReportLab

## Roles

- `admin`
- `organizer`
- `user`

## Seed Accounts

- Admin: `admin@eventsphere.local` / `Admin123!`
- Organizer: `organizer@eventsphere.local` / `Organizer123!`
- User: `user@eventsphere.local` / `User123!`

The app also seeds a few extra demo attendees so organizer and admin reports have realistic sample data on first run.

## Seeded Event Examples

First run adds at least six realistic Kazakhstan-based events, including:

- a tech summit in Almaty
- a startup breakfast in Astana
- a university club event
- a live music event
- a workshop
- a conference

## Booking and Payment Simulation Flow

1. Browse events on `Discover events`.
2. Open an event detail page.
3. Click `Book ticket`.
4. Choose a seat category, row, and available seat.
5. EventSphere creates a `pending_payment` booking and marks that seat as `reserved_pending_payment`.
6. The user is redirected to the sandbox payment waiting page.
7. The waiting page shows the amount, booking ID, payment reference, deadline, and a QR code only.
8. The QR opens a dedicated confirmation page with a secure token.
9. Confirming payment on that QR page marks the payment as confirmed, converts the seat to `sold`, creates the digital ticket, and writes an email log with the ticket attachment path.
10. The ticket page shows the QR ticket, seat details, delivery status, and download action.

No real money is charged anywhere in the flow.

Pending bookings automatically expire after the configured payment window and release their reserved seats back to inventory.

## Organizer Features

- KPI overview for events, ticket sales, revenue, check-ins, and fill rate
- create, edit, and cancel events
- attendee table per event with seat and payment details
- seat inventory view per event with available, reserved, sold, and blocked states
- organizer-only check-in validation for owned events
- revenue, ticketing, attendance, and category reports

## Admin Features

- platform KPIs for users, organizers, events, bookings, and revenue
- recent bookings view
- manage users and deactivate accounts
- manage events and cancel them globally
- global reports for revenue, sold tickets, attendance, category demand, bookings, payments, tickets, and email logs
- CSV export for bookings, payments, tickets, and email logs

## Run Locally

```bash
cd /path/to/APM_FInal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

You can also run:

```bash
streamlit run app.py
```

## Database Notes

- default database path: `data/eventsphere.db`
- override with `DATABASE_URL`
- the database is created, migrated, and seeded automatically on first run
- ticket files are generated under `data/tickets/`

## Environment Variables

- `DATABASE_URL`: optional custom database connection string
- `PUBLIC_APP_URL`: base URL used in payment and ticket QR payloads
- `PAYMENT_WINDOW_MINUTES`: optional sandbox payment expiration window

## Deployment Notes

This app is designed to stay deployable on Streamlit Cloud:

- keep `streamlit_app.py` as the entry file
- deploy from the GitHub branch Streamlit Cloud watches
- automatic redeploy should happen whenever that branch is pushed

For real long-term persistence in production, replace SQLite with a managed database. On Streamlit Cloud, SQLite is suitable for demos and light usage, but not for guaranteed durable storage across all infrastructure events.

## Screenshots

Add screenshots here after running the upgraded app:

- Discover page
- Event detail page
- Payment simulator
- Ticket view
- Organizer dashboard
- Admin dashboard
