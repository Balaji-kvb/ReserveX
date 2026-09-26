from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

bookings = {}

USER_SERVICE_URL = "http://localhost:5001"
EVENT_SERVICE_URL = "http://localhost:5002"


@app.get("/health")
def health():
    return jsonify({
        "service": "booking-service",
        "status": "healthy"
    })


@app.post("/bookings")
def create_booking():
    data = request.get_json()

    user_id = data["user_id"]
    event_id = data["event_id"]

    # Step 1: Ask User Service whether the user exists
    user_response = requests.get(
        f"{USER_SERVICE_URL}/users/{user_id}"
    )

    if user_response.status_code != 200:
        return jsonify({
            "error": "User not found"
        }), 404

    # Step 2: Ask Event Service whether a slot exists
    availability_response = requests.get(
        f"{EVENT_SERVICE_URL}/events/{event_id}/availability"
    )

    if availability_response.status_code != 200:
        return jsonify({
            "error": "Event not found"
        }), 404

    availability = availability_response.json()

    if availability["available_slots"] <= 0:
        return jsonify({
            "error": "No slots available"
        }), 409

    # Step 3: Reserve the slot through Event Service
    reserve_response = requests.post(
        f"{EVENT_SERVICE_URL}/events/{event_id}/reserve"
    )

    if reserve_response.status_code != 200:
        return jsonify({
            "error": "Unable to reserve slot"
        }), 409

    # Step 4: Create local booking record
    booking_id = len(bookings) + 1

    booking = {
        "id": booking_id,
        "user_id": user_id,
        "event_id": event_id,
        "status": "CONFIRMED"
    }

    bookings[booking_id] = booking

    return jsonify(booking), 201


@app.get("/bookings/<int:booking_id>")
def get_booking(booking_id):
    booking = bookings.get(booking_id)

    if booking is None:
        return jsonify({
            "error": "Booking not found"
        }), 404

    return jsonify(booking)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5003,
        debug=True
    )