"""
Integration tests for Booking Service.
Tests the full orchestration flow across all three services.
Requires User Service (5001) and Event Service (5002) to be running.
"""

import requests
import time

BASE_URL = "http://localhost:5003"
USER_SERVICE = "http://localhost:5001"
EVENT_SERVICE = "http://localhost:5002"


def setup():
    """Create a user and event for testing."""
    ts = int(time.time())
    user_resp = requests.post(
        f"{USER_SERVICE}/users",
        json={"name": "Booking Tester", "email": f"booking_test_{ts}@test.com"}
    )
    user_id = user_resp.json()["id"]

    event_resp = requests.post(
        f"{EVENT_SERVICE}/events",
        json={"name": f"Booking Test Event {ts}", "total_slots": 10}
    )
    event_id = event_resp.json()["id"]

    print(f"Setup: user_id={user_id}, event_id={event_id}")
    return user_id, event_id


def test_health():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "booking-service"
    print("✅ test_health passed")


def test_create_booking(user_id, event_id):
    resp = requests.post(
        f"{BASE_URL}/bookings",
        json={"user_id": user_id, "event_id": event_id}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["event_id"] == event_id
    assert data["status"] == "CONFIRMED"
    print(f"✅ test_create_booking passed (id={data['id']})")
    return data["id"]


def test_get_booking(booking_id):
    resp = requests.get(f"{BASE_URL}/bookings/{booking_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == booking_id
    print("✅ test_get_booking passed")


def test_booking_not_found():
    resp = requests.get(f"{BASE_URL}/bookings/99999")
    assert resp.status_code == 404
    print("✅ test_booking_not_found passed")


def test_invalid_user(event_id):
    resp = requests.post(
        f"{BASE_URL}/bookings",
        json={"user_id": 99999, "event_id": event_id}
    )
    assert resp.status_code == 404
    assert "User not found" in resp.json()["error"]
    print("✅ test_invalid_user passed")


def test_invalid_event(user_id):
    resp = requests.post(
        f"{BASE_URL}/bookings",
        json={"user_id": user_id, "event_id": 99999}
    )
    assert resp.status_code == 404
    assert "Event not found" in resp.json()["error"]
    print("✅ test_invalid_event passed")


def test_cancel_booking(booking_id, event_id):
    # Get availability before cancel
    avail_before = requests.get(f"{EVENT_SERVICE}/events/{event_id}/availability").json()["available_slots"]

    resp = requests.post(f"{BASE_URL}/bookings/{booking_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    # Verify slot was released
    avail_after = requests.get(f"{EVENT_SERVICE}/events/{event_id}/availability").json()["available_slots"]
    assert avail_after == avail_before + 1
    print("✅ test_cancel_booking passed (slot released)")


def test_sold_out_booking(user_id):
    """Create event with 1 slot, book it, then try another."""
    ts = int(time.time())
    event_resp = requests.post(
        f"{EVENT_SERVICE}/events",
        json={"name": f"Sold Out Test {ts}", "total_slots": 1}
    )
    event_id = event_resp.json()["id"]

    # First booking should succeed
    resp1 = requests.post(
        f"{BASE_URL}/bookings",
        json={"user_id": user_id, "event_id": event_id}
    )
    assert resp1.status_code == 201

    # Create a second user for the next attempt
    user2 = requests.post(
        f"{USER_SERVICE}/users",
        json={"name": "User2", "email": f"user2_{ts}@test.com"}
    ).json()["id"]

    # Second booking should fail — sold out
    resp2 = requests.post(
        f"{BASE_URL}/bookings",
        json={"user_id": user2, "event_id": event_id}
    )
    assert resp2.status_code == 409
    assert "No slots available" in resp2.json()["error"]
    print("✅ test_sold_out_booking passed")


def test_missing_fields():
    resp = requests.post(f"{BASE_URL}/bookings", json={"user_id": 1})
    assert resp.status_code == 400
    print("✅ test_missing_fields passed")


def test_metrics():
    resp = requests.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "booking_requests_total" in text
    assert "successful_bookings_total" in text
    assert "failed_bookings_total" in text
    print("✅ test_metrics passed")


if __name__ == "__main__":
    print("=== Booking Service Tests ===")
    user_id, event_id = setup()
    test_health()
    booking_id = test_create_booking(user_id, event_id)
    test_get_booking(booking_id)
    test_booking_not_found()
    test_invalid_user(event_id)
    test_invalid_event(user_id)
    test_cancel_booking(booking_id, event_id)
    test_sold_out_booking(user_id)
    test_missing_fields()
    test_metrics()
    print("\n✅ All Booking Service tests passed!")
