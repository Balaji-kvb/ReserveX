"""
Database connection module for Booking Service.

WHY: Same centralized pool pattern. Booking Service stores booking records.
It does NOT directly access users or events tables — it calls the other
services via REST API (microservice rule).
"""

import os
import psycopg_pool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://reservex:REPLACE_ME_PASSWORD@localhost:5432/reservex"
)

pool = psycopg_pool.ConnectionPool(
    DATABASE_URL,
    min_size=2,
    max_size=10,
    open=True
)


def get_db():
    """Get a database connection from the pool."""
    return pool.connection()


def init_db():
    """Create the bookings table if it doesn't exist."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id          SERIAL PRIMARY KEY,
                    user_id     INTEGER NOT NULL,
                    event_id    INTEGER NOT NULL,
                    status      VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
                    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            # Idempotency index: one active booking per user per event
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_unique_active
                    ON bookings(user_id, event_id) WHERE status = 'CONFIRMED'
            """)
            conn.commit()
