-- ReserveX: Complete database initialization
-- Run this against the 'reservex' database

-- ============================================================
-- USERS TABLE (owned by User Service)
-- ============================================================
-- Stores registered users. Each user has a unique email.
-- The User Service is the sole owner of this table.

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index on email for fast lookup during duplicate checks
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);


-- ============================================================
-- EVENTS TABLE (owned by Event Service)
-- ============================================================
-- Stores events with inventory tracking.
-- available_slots is the authoritative inventory counter.
-- The Event Service is the sole owner of this table.
-- CHECK constraint prevents available_slots from going negative
-- at the database level — a safety net even if application logic fails.

CREATE TABLE IF NOT EXISTS events (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    total_slots      INTEGER NOT NULL CHECK (total_slots > 0),
    available_slots  INTEGER NOT NULL CHECK (available_slots >= 0),
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- available_slots can never exceed total_slots
    CONSTRAINT slots_within_bounds CHECK (available_slots <= total_slots)
);


-- ============================================================
-- BOOKINGS TABLE (owned by Booking Service)
-- ============================================================
-- Stores booking records. References user_id and event_id
-- but does NOT use foreign keys across service boundaries
-- because in a real microservice architecture, each service
-- owns its own database. We store the IDs for reference only.
--
-- status: CONFIRMED, CANCELLED

CREATE TABLE IF NOT EXISTS bookings (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    event_id    INTEGER NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for looking up bookings by user or event
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_event_id ON bookings(event_id);
-- Index for idempotency: prevent duplicate active bookings
CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_unique_active
    ON bookings(user_id, event_id) WHERE status = 'CONFIRMED';
