"""
Database connection module for Event Service.

WHY: Same pattern as User Service — centralized connection pooling.
Event Service is the AUTHORITATIVE OWNER of event/inventory data.
The atomic reservation query lives in app.py's reserve endpoint,
but the connection comes from here.
"""

import os
import psycopg_pool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://reservex:REPLACE_ME_LOCAL_DEV@localhost:5432/reservex"
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
    """Create the events table if it doesn't exist."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id               SERIAL PRIMARY KEY,
                    name             VARCHAR(255) NOT NULL,
                    total_slots      INTEGER NOT NULL CHECK (total_slots > 0),
                    available_slots  INTEGER NOT NULL CHECK (available_slots >= 0),
                    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    CONSTRAINT slots_within_bounds CHECK (available_slots <= total_slots)
                )
            """)
            conn.commit()
