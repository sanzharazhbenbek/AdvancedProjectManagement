from __future__ import annotations

from sqlalchemy import inspect, text

from db.database import get_engine


SCHEMA_UPDATES = {
    "bookings": {
        "seat_id": "INTEGER",
        "payment_deadline": "DATETIME",
        "payment_confirmation_token": "VARCHAR(120)",
        "customer_email": "VARCHAR(180)",
    },
    "tickets": {
        "seat_id": "INTEGER",
        "category": "VARCHAR(40)",
        "row_label": "VARCHAR(10)",
        "seat_number": "INTEGER",
        "price_kzt": "INTEGER",
        "ticket_file_path": "VARCHAR(500)",
    },
    "payment_simulations": {
        "confirmed_url_path": "VARCHAR(500)",
    },
}


def migrate_database_if_needed() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        for table_name, columns in SCHEMA_UPDATES.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
