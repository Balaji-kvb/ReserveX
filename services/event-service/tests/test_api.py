"""
Integration tests for Event Service.
Tests REST API endpoints including the critical atomic reservation.
"""

import requests
import time

BASE_URL = "http://localhost:5002"


def test_health():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "event-service"
    print("✅ test_health passed")


def test_create_event():
    resp = requests.post(
        f"{BASE_URL}/events",
        json={"name": f"Test Event {int(time.time())}", "total_slots": 100}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_slots"] == 100
    assert data["available_slots"] == 100
    print(f"✅ test_create_event passed (id={data['id']})")
    return data["id"]


def test_get_event(event_id):
    resp = requests.get(f"{BASE_URL}/events/{event_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == event_id
    print(f"✅ test_get_event passed")


def test_event_not_found():
    resp = requests.get(f"{BASE_URL}/events/99999")
    assert resp.status_code == 404
    print("✅ test_event_not_found passed")


def test_availability(event_id):
    resp = requests.get(f"{BASE_URL}/events/{event_id}/availability")
    assert resp.status_code == 200
    assert resp.json()["available_slots"] == 100
    print("✅ test_availability passed")


def test_reserve_slot(event_id):
    resp = requests.post(f"{BASE_URL}/events/{event_id}/reserve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available_slots"] == 99
    assert data["message"] == "Slot reserved successfully"
    print("✅ test_reserve_slot passed")


def test_release_slot(event_id):
    resp = requests.post(f"{BASE_URL}/events/{event_id}/release")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available_slots"] == 100  # Back to full
    print("✅ test_release_slot passed")


def test_sold_out():
    """Create an event with 1 slot, reserve it, then try again."""
    resp = requests.post(
        f"{BASE_URL}/events",
        json={"name": f"Sold Out Test {int(time.time())}", "total_slots": 1}
    )
    event_id = resp.json()["id"]

    # Reserve the only slot
    resp = requests.post(f"{BASE_URL}/events/{event_id}/reserve")
    assert resp.status_code == 200

    # Try to reserve again — should fail
    resp = requests.post(f"{BASE_URL}/events/{event_id}/reserve")
    assert resp.status_code == 409
    assert resp.json()["error"] == "No slots available"
    print("✅ test_sold_out passed")


def test_invalid_slots():
    resp = requests.post(
        f"{BASE_URL}/events",
        json={"name": "Bad Event", "total_slots": -5}
    )
    assert resp.status_code == 400
    print("✅ test_invalid_slots passed")


def test_metrics():
    resp = requests.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200
    assert "reservation_attempts_total" in resp.text
    print("✅ test_metrics passed")


if __name__ == "__main__":
    print("=== Event Service Tests ===")
    test_health()
    event_id = test_create_event()
    test_get_event(event_id)
    test_event_not_found()
    test_availability(event_id)
    test_reserve_slot(event_id)
    test_release_slot(event_id)
    test_sold_out()
    test_invalid_slots()
    test_metrics()
    print("\n✅ All Event Service tests passed!")
