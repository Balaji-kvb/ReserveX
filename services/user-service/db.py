"""
Database connection module for User Service.

WHY: Centralizes database connection logic so app.py doesn't manage
connection strings or pooling directly. Uses psycopg 3's connection pool
for efficient connection reuse.

HOW: Creates a connection pool on module load. Provides a get_db()
function that returns a connection from the pool.
"""

import os
import psycopg_pool

# Read database configuration from environment variables.
# This allows the same code to work locally, in Docker, and in Kubernetes
# by simply changing environment variables.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://reservex:REPLACE_ME_LOCAL_DEV@localhost:5432/reservex"
)

# Connection pool: reuses connections instead of opening a new one per request.
# min_size=2: always keep 2 connections ready
# max_size=10: never open more than 10 connections
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
    """Create the users table if it doesn't exist.

    This is a safety net — the main schema is in database/init/001_schema.sql.
    Running it here means the service can self-initialize in development.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id          SERIAL PRIMARY KEY,
                    name        VARCHAR(255) NOT NULL,
                    email       VARCHAR(255) NOT NULL UNIQUE,
                    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            conn.commit()
