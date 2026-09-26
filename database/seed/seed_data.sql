-- Seed data for development/testing
-- Run after 001_schema.sql

-- Sample users
INSERT INTO users (name, email) VALUES
    ('Venkata Balaji', 'balaji@example.com'),
    ('Test User', 'test@example.com')
ON CONFLICT (email) DO NOTHING;

-- Sample event
INSERT INTO events (name, total_slots, available_slots) VALUES
    ('LPU TechFest 2026', 1000, 1000)
ON CONFLICT DO NOTHING;
