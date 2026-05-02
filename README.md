# EventSphere

EventSphere is a Streamlit-based event and ticketing management platform built to feel closer to a production-style SaaS workflow than a classroom MVP. It supports event discovery, role-based authentication, organizer operations, simulated Kaspi-style payments, QR tickets, and QR/manual attendance check-in.

## What’s Included

- public event discovery with search, filters, sorting, and featured content
- role-based sign in, account creation, and session-aware navigation
- secure password hashing with PBKDF2
- SQLite persistence through SQLAlchemy
- pending booking flow with sandbox payment confirmation
- QR ticket generation and per-ticket validation
- organizer dashboards with KPIs, event management, attendee lists, and reports
- admin dashboards with user/event management and platform reporting
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
4. EventSphere creates a `pending_payment` booking.
5. The user is redirected to the sandbox payment page.
6. The payment page shows the amount, booking ID, payment reference, deadline, and a QR code pointing back to the Streamlit payment route.
7. Clicking `I have paid / Confirm payment` marks the booking as paid, creates the digital ticket, and generates the QR ticket payload.
8. The user is redirected to the ticket page.

No real money is charged anywhere in the flow.

## Organizer Features

- KPI overview for events, ticket sales, revenue, check-ins, and fill rate
- create, edit, and cancel events
- attendee table per event
- organizer-only check-in validation for owned events
- revenue, ticketing, attendance, and category reports

## Admin Features

- platform KPIs for users, organizers, events, bookings, and revenue
- recent bookings view
- manage users and deactivate accounts
- manage events and cancel them globally
- global reports for revenue, sold tickets, attendance, and category demand

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
- the database is created and seeded automatically on first run

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
