"""
Event Service — ReserveX

Responsibilities:
- Create event (POST /events)
- Retrieve event (GET /events/<id>)
- Check availability (GET /events/<id>/availability)
- Reserve one slot ATOMICALLY (POST /events/<id>/reserve)
- Release one slot for compensation (POST /events/<id>/release)
- Health check (GET /health)
- Prometheus metrics (GET /metrics)

This service is the AUTHORITATIVE OWNER of event inventory.
The atomic reservation query (UPDATE ... WHERE available_slots > 0 RETURNING ...)
is the core concurrency-safety mechanism of the entire project.
"""

from flask import Flask, jsonify, request
from psycopg.rows import dict_row
from prometheus_client import Counter, Histogram, generate_latest
import time

from db import get_db, init_db

app = Flask(__name__)

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

# Business metrics — these tell the story of the reservation system
RESERVATION_ATTEMPTS = Counter(
    "reservation_attempts_total",
    "Total reservation attempts"
)

RESERVATION_SUCCESS = Counter(
    "reservation_success_total",
    "Successful reservations"
)

RESERVATION_FAILURE = Counter(
    "reservation_failure_total",
    "Failed reservations (sold out or not found)"
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
        "service": "event-service",
        "status": "healthy"
    })


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.post("/events")
def create_event():
    data = request.get_json()

    if not data or "name" not in data or "total_slots" not in data:
        return jsonify({"error": "name and total_slots are required"}), 400

    total_slots = data["total_slots"]
    if not isinstance(total_slots, int) or total_slots <= 0:
        return jsonify({"error": "total_slots must be a positive integer"}), 400

    try:
        with get_db() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO events (name, total_slots, available_slots)
                    VALUES (%s, %s, %s)
                    RETURNING id, name, total_slots, available_slots, created_at
                    """,
                    (data["name"], total_slots, total_slots)
                )
                event = cur.fetchone()
                conn.commit()

                event["created_at"] = event["created_at"].isoformat()
                return jsonify(event), 201

    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.get("/events/<int:event_id>")
def get_event(event_id):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, name, total_slots, available_slots, created_at FROM events WHERE id = %s",
                (event_id,)
            )
            event = cur.fetchone()

    if event is None:
        return jsonify({"error": "Event not found"}), 404

    event["created_at"] = event["created_at"].isoformat()
    return jsonify(event)


@app.get("/events/<int:event_id>/availability")
def get_availability(event_id):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, available_slots FROM events WHERE id = %s",
                (event_id,)
            )
            event = cur.fetchone()

    if event is None:
        return jsonify({"error": "Event not found"}), 404

    return jsonify({
        "event_id": event_id,
        "available_slots": event["available_slots"]
    })


@app.post("/events/<int:event_id>/reserve")
def reserve_slot(event_id):
    """
    ATOMIC RESERVATION — the most critical operation in the system.

    This single UPDATE statement does three things atomically:
    1. Checks if the event exists
    2. Checks if available_slots > 0
    3. Decrements available_slots by 1

    If the WHERE clause matches no rows, either:
    - The event doesn't exist, OR
    - available_slots is already 0 (sold out)

    WHY this is concurrency-safe:
    PostgreSQL's UPDATE acquires a row-level lock. Even if 1000 requests
    hit this endpoint simultaneously, they are serialized at the row level.
    Each UPDATE sees the result of the previous one's commit.

    This prevents overselling WITHOUT needing:
    - SELECT + application logic + UPDATE (race condition!)
    - Explicit table locks
    - Redis/distributed locks
    """
    RESERVATION_ATTEMPTS.inc()

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE events
                SET available_slots = available_slots - 1
                WHERE id = %s AND available_slots > 0
                RETURNING id, available_slots
                """,
                (event_id,)
            )
            result = cur.fetchone()
            conn.commit()

    if result is None:
        RESERVATION_FAILURE.inc()

        # Distinguish between "not found" and "sold out"
        with get_db() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id FROM events WHERE id = %s", (event_id,))
                exists = cur.fetchone()

        if exists is None:
            return jsonify({"error": "Event not found"}), 404
        else:
            return jsonify({"error": "No slots available"}), 409

    RESERVATION_SUCCESS.inc()
    return jsonify({
        "event_id": event_id,
        "available_slots": result["available_slots"],
        "message": "Slot reserved successfully"
    })


@app.post("/events/<int:event_id>/release")
def release_slot(event_id):
    """
    COMPENSATION endpoint — releases a previously reserved slot.

    WHY: If Booking Service successfully reserves a slot but then fails
    to create the booking record, it calls this endpoint to undo the
    reservation. This is a simple compensation pattern, NOT a distributed
    transaction.

    The atomic UPDATE ensures we never exceed total_slots.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE events
                SET available_slots = available_slots + 1
                WHERE id = %s AND available_slots < total_slots
                RETURNING id, available_slots
                """,
                (event_id,)
            )
            result = cur.fetchone()
            conn.commit()

    if result is None:
        return jsonify({"error": "Event not found or already at full capacity"}), 404

    return jsonify({
        "event_id": event_id,
        "available_slots": result["available_slots"],
        "message": "Slot released successfully"
    })


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5002, debug=True)
