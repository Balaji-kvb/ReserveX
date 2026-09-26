"""
User Service — ReserveX

Responsibilities:
- Create user (POST /users)
- Retrieve user (GET /users/<id>)
- Health check (GET /health)
- Prometheus metrics (GET /metrics)

This service OWNS the users table in PostgreSQL.
No other service should directly access user data.
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
# Counters: track cumulative totals (only go up)
# Histograms: track distribution of values (like response times)

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


@app.before_request
def before_request():
    """Record the start time of each request for duration tracking."""
    request._start_time = time.time()


@app.after_request
def after_request(response):
    """Record metrics after each request completes."""
    # Skip recording metrics for the /metrics endpoint itself
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
        "service": "user-service",
        "status": "healthy"
    })


@app.get("/metrics")
def metrics():
    """Prometheus scrapes this endpoint to collect metrics."""
    return generate_latest(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.post("/users")
def create_user():
    data = request.get_json()

    # Validate required fields
    if not data or "name" not in data or "email" not in data:
        return jsonify({"error": "name and email are required"}), 400

    try:
        with get_db() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO users (name, email)
                    VALUES (%s, %s)
                    RETURNING id, name, email, created_at
                    """,
                    (data["name"], data["email"])
                )
                user = cur.fetchone()
                conn.commit()

                # Convert timestamp to string for JSON
                user["created_at"] = user["created_at"].isoformat()
                return jsonify(user), 201

    except Exception as e:
        error_msg = str(e)
        if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
            return jsonify({"error": "Email already exists"}), 409
        return jsonify({"error": f"Database error: {error_msg}"}), 500


@app.get("/users/<int:user_id>")
def get_user(user_id):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, name, email, created_at FROM users WHERE id = %s",
                (user_id,)
            )
            user = cur.fetchone()

    if user is None:
        return jsonify({"error": "User not found"}), 404

    user["created_at"] = user["created_at"].isoformat()
    return jsonify(user)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=True)