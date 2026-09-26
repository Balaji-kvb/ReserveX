"""
Booking Service — ReserveX

Responsibilities:
- Create booking with full orchestration (POST /bookings)
- Retrieve booking (GET /bookings/<id>)
- Cancel booking with compensation (POST /bookings/<id>/cancel)
- Health check (GET /health)
- Prometheus metrics (GET /metrics)

This service is the ORCHESTRATOR:
1. Validates user via User Service REST API
2. Reserves slot via Event Service REST API (atomic)
3. Creates booking record in its own PostgreSQL table
4. If step 3 fails, calls Event Service /release (compensation)

IMPORTANT: This service does NOT access users or events tables directly.
Communication between services happens through REST APIs.
"""

import os
import time

from flask import Flask, jsonify, request
from psycopg.rows import dict_row
from prometheus_client import Counter, Histogram, generate_latest
import requests as http_client

from db import get_db, init_db

app = Flask(__name__)

# Service URLs — configurable via environment variables.
# Locally: localhost. Docker: container names. Kubernetes: service names.
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
EVENT_SERVICE_URL = os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002")

# ============================================================
# Prometheus Metrics
# ============================================================

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

# Business metrics
BOOKING_REQUESTS = Counter(
    "booking_requests_total",
    "Total booking requests received"
)

SUCCESSFUL_BOOKINGS = Counter(
    "successful_bookings_total",
    "Bookings that completed successfully"
)

FAILED_BOOKINGS = Counter(
    "failed_bookings_total",
    "Bookings that failed",
    ["reason"]
)


@app.before_request
def before_request():
    request._start_time = time.time()


@app.after_request
def after_request(response):
    if request.path != "/metrics":
        duration = time.time() - getattr(request, "_start_time", time.time())
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.path,
            status=response.status_code
        ).inc()
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.path
        ).observe(duration)
    return response


# ============================================================
# Endpoints
# ============================================================

@app.get("/health")
def health():
    return jsonify({
        "service": "booking-service",
        "status": "healthy"
    })


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.post("/bookings")
def create_booking():
    """
    Full booking orchestration flow:

    1. Validate input
    2. Verify user exists (call User Service)
    3. Reserve slot atomically (call Event Service)
    4. Create booking record in our database
    5. If step 4 fails, compensate by releasing the slot

    This is NOT a distributed transaction. It uses a simple
    compensation pattern. Documented limitation: if the compensation
    call also fails, a slot is "leaked". For this academic project,
    that edge case is acknowledged but not solved with a saga framework.
    """
    BOOKING_REQUESTS.inc()

    data = request.get_json()
    if not data or "user_id" not in data or "event_id" not in data:
        FAILED_BOOKINGS.labels(reason="bad_request").inc()
        return jsonify({"error": "user_id and event_id are required"}), 400

    user_id = data["user_id"]
    event_id = data["event_id"]

    # Step 1: Validate user exists via User Service
    try:
        user_response = http_client.get(
            f"{USER_SERVICE_URL}/users/{user_id}",
            timeout=5
        )
    except http_client.RequestException:
        FAILED_BOOKINGS.labels(reason="user_service_unavailable").inc()
        return jsonify({"error": "User Service unavailable"}), 503

    if user_response.status_code != 200:
        FAILED_BOOKINGS.labels(reason="user_not_found").inc()
        return jsonify({"error": "User not found"}), 404

    # Step 2: Reserve slot atomically via Event Service
    try:
        reserve_response = http_client.post(
            f"{EVENT_SERVICE_URL}/events/{event_id}/reserve",
            timeout=5
        )
    except http_client.RequestException:
        FAILED_BOOKINGS.labels(reason="event_service_unavailable").inc()
        return jsonify({"error": "Event Service unavailable"}), 503

    if reserve_response.status_code == 404:
        FAILED_BOOKINGS.labels(reason="event_not_found").inc()
        return jsonify({"error": "Event not found"}), 404

    if reserve_response.status_code == 409:
        FAILED_BOOKINGS.labels(reason="sold_out").inc()
        return jsonify({"error": "No slots available"}), 409

    if reserve_response.status_code != 200:
        FAILED_BOOKINGS.labels(reason="reservation_failed").inc()
        return jsonify({"error": "Unable to reserve slot"}), 409

    # Step 3: Create booking record in our database
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO bookings (user_id, event_id, status)
                    VALUES (%s, %s, 'CONFIRMED')
                    RETURNING id, user_id, event_id, status, created_at
                    """,
                    (user_id, event_id)
                )
                booking = cur.fetchone()
                conn.commit()

    except Exception as e:
        # COMPENSATION: If booking record creation fails,
        # release the slot we just reserved
        try:
            http_client.post(
                f"{EVENT_SERVICE_URL}/events/{event_id}/release",
                timeout=5
            )
        except http_client.RequestException:
            # Compensation also failed — log this but don't crash
            app.logger.error(
                f"COMPENSATION FAILED: Could not release slot for event {event_id} "
                f"after booking creation failed: {str(e)}"
            )

        error_msg = str(e)
        if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
            # Idempotency: user already has an active booking for this event
            # Release the slot we just reserved (duplicate booking)
            FAILED_BOOKINGS.labels(reason="duplicate_booking").inc()
            return jsonify({"error": "Active booking already exists for this user and event"}), 409

        FAILED_BOOKINGS.labels(reason="database_error").inc()
        return jsonify({"error": f"Booking creation failed: {error_msg}"}), 500

    SUCCESSFUL_BOOKINGS.inc()
    booking["created_at"] = booking["created_at"].isoformat()
    return jsonify(booking), 201


@app.get("/bookings/<int:booking_id>")
def get_booking(booking_id):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, user_id, event_id, status, created_at FROM bookings WHERE id = %s",
                (booking_id,)
            )
            booking = cur.fetchone()

    if booking is None:
        return jsonify({"error": "Booking not found"}), 404

    booking["created_at"] = booking["created_at"].isoformat()
    return jsonify(booking)


@app.post("/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id):
    """
    Cancel a booking and release the reserved slot back.

    Steps:
    1. Find the booking
    2. Update status to CANCELLED
    3. Call Event Service /release to return the slot
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Find and update the booking in one atomic operation
            cur.execute(
                """
                UPDATE bookings
                SET status = 'CANCELLED'
                WHERE id = %s AND status = 'CONFIRMED'
                RETURNING id, user_id, event_id, status, created_at
                """,
                (booking_id,)
            )
            booking = cur.fetchone()
            conn.commit()

    if booking is None:
        return jsonify({"error": "Booking not found or already cancelled"}), 404

    # Release the slot back to Event Service
    try:
        http_client.post(
            f"{EVENT_SERVICE_URL}/events/{booking['event_id']}/release",
            timeout=5
        )
    except http_client.RequestException:
        app.logger.error(
            f"WARNING: Booking {booking_id} cancelled but slot release failed "
            f"for event {booking['event_id']}"
        )

    booking["created_at"] = booking["created_at"].isoformat()
    return jsonify(booking)


if __name__ == "__main__":
    init_db()
    app.run(
        host="0.0.0.0",
        port=5003,
        debug=True
    )