-- Seed data for development/testing
-- Run after 001_schema.sql

-- Delete existing data
TRUNCATE TABLE bookings, events, users RESTART IDENTITY CASCADE;

-- Insert a massive number of users for k6 load testing (e.g. 500,000 users)
-- IDs will be from 1 to 500000
INSERT INTO users (id, name, email)
SELECT 
    i, 
    'Load Test User ' || i, 
    'user' || i || '@loadtest.com'
FROM generate_series(1, 500000) AS i;

-- Insert 10 events with massive capacity
INSERT INTO events (id, name, total_slots, available_slots)
SELECT 
    i, 
    'Massive Load Test Event ' || i, 
    1000000, 
    1000000
FROM generate_series(1, 10) AS i;
