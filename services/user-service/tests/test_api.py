"""
Integration tests for User Service.
Tests the REST API endpoints against a real PostgreSQL database.
"""

import requests
import time

BASE_URL = "http://localhost:5001"


def test_health():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "user-service"
    assert data["status"] == "healthy"
    print("✅ test_health passed")


def test_create_user():
    email = f"test_{int(time.time())}@example.com"
    resp = requests.post(
        f"{BASE_URL}/users",
        json={"name": "Test User", "email": email}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test User"
    assert data["email"] == email
    assert "id" in data
    assert "created_at" in data
    print(f"✅ test_create_user passed (id={data['id']})")
    return data["id"]


def test_get_user(user_id):
    resp = requests.get(f"{BASE_URL}/users/{user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user_id
    print(f"✅ test_get_user passed (id={user_id})")


def test_user_not_found():
    resp = requests.get(f"{BASE_URL}/users/99999")
    assert resp.status_code == 404
    assert "error" in resp.json()
    print("✅ test_user_not_found passed")


def test_duplicate_email():
    email = f"dup_{int(time.time())}@example.com"
    resp1 = requests.post(
        f"{BASE_URL}/users",
        json={"name": "First", "email": email}
    )
    assert resp1.status_code == 201

    resp2 = requests.post(
        f"{BASE_URL}/users",
        json={"name": "Second", "email": email}
    )
    assert resp2.status_code == 409
    print("✅ test_duplicate_email passed")


def test_missing_fields():
    resp = requests.post(f"{BASE_URL}/users", json={"name": "No Email"})
    assert resp.status_code == 400
    print("✅ test_missing_fields passed")


def test_metrics():
    resp = requests.get(f"{BASE_URL}/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
    print("✅ test_metrics passed")


if __name__ == "__main__":
    print("=== User Service Tests ===")
    test_health()
    user_id = test_create_user()
    test_get_user(user_id)
    test_user_not_found()
    test_duplicate_email()
    test_missing_fields()
    test_metrics()
    print("\n✅ All User Service tests passed!")
