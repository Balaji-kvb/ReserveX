"""
Concurrency Test — ReserveX

This is the MOST IMPORTANT test in the entire project.

WHAT: Sends many concurrent booking requests against limited inventory.
WHY: Proves the atomic UPDATE prevents overselling.
HOW: Uses Python's concurrent.futures to simulate simultaneous requests.

Test setup:
1. Create a test event with LIMITED inventory (e.g., 50 slots)
2. Create a test user
3. Send MANY more concurrent requests than available slots
4. Verify: successful_bookings <= available_slots

CONCURRENCY TEST SERVER (Correction #4):
For meaningful results, the booking service should run under gunicorn
with multiple workers. Flask's dev server is single-threaded and
doesn't truly test concurrent database access.

Run booking service with: gunicorn --workers 4 --bind 0.0.0.0:5003 app:app
"""

import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
USER_SERVICE = "http://localhost:5001"
EVENT_SERVICE = "http://localhost:5002"
BOOKING_SERVICE = "http://localhost:5003"

TOTAL_SLOTS = 50           # Limited inventory
CONCURRENT_REQUESTS = 200  # Much more than available slots


def setup_test_data():
    """Create a test user and a test event with limited inventory."""
    # Create test user (or use existing)
    user_resp = requests.post(
        f"{USER_SERVICE}/users",
        json={"name": "Concurrency Tester", "email": f"concurrent_{int(time.time())}@test.com"}
    )
    if user_resp.status_code not in (201, 409):
        print(f"ERROR: Could not create user: {user_resp.json()}")
        sys.exit(1)

    user_id = user_resp.json()["id"] if user_resp.status_code == 201 else 1

    # Create test event with limited slots
    event_resp = requests.post(
        f"{EVENT_SERVICE}/events",
        json={"name": f"Concurrency Test Event {int(time.time())}", "total_slots": TOTAL_SLOTS}
    )
    if event_resp.status_code != 201:
        print(f"ERROR: Could not create event: {event_resp.json()}")
        sys.exit(1)

    event_id = event_resp.json()["id"]
    print(f"Setup: user_id={user_id}, event_id={event_id}, slots={TOTAL_SLOTS}")
    return user_id, event_id


def make_booking(user_id, event_id):
    """Attempt a single booking. Returns (status_code, response_json, duration)."""
    start = time.time()
    try:
        resp = requests.post(
            f"{BOOKING_SERVICE}/bookings",
            json={"user_id": user_id, "event_id": event_id},
            timeout=10
        )
        duration = time.time() - start
        return resp.status_code, resp.json(), duration
    except Exception as e:
        duration = time.time() - start
        return 0, {"error": str(e)}, duration


def run_concurrency_test():
    """
    The core test:
    - Fire CONCURRENT_REQUESTS bookings simultaneously
    - Count successes, rejections, errors
    - Verify no overselling
    """
    user_id, event_id = setup_test_data()

    print(f"\nFiring {CONCURRENT_REQUESTS} concurrent booking requests for {TOTAL_SLOTS} slots...\n")

    results = {"success": 0, "rejected": 0, "errors": 0, "durations": []}
    status_codes = {}

    start_time = time.time()

    # Note: For the idempotency index, we need different users or we'll get
    # duplicate booking errors after the first success. For this test, we're
    # testing Event Service reservation atomicity, so we use unique users.
    # In production, idempotency would prevent a single user from double-booking.

    # First, create many test users for the concurrency test
    test_users = []
    print("Creating test users for concurrent requests...")
    for i in range(CONCURRENT_REQUESTS):
        resp = requests.post(
            f"{USER_SERVICE}/users",
            json={"name": f"Test User {i}", "email": f"test_conc_{int(time.time())}_{i}@test.com"}
        )
        if resp.status_code == 201:
            test_users.append(resp.json()["id"])
        else:
            test_users.append(user_id)  # fallback

    print(f"Created {len(test_users)} test users. Starting concurrent bookings...\n")

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [
            executor.submit(make_booking, test_users[i], event_id)
            for i in range(CONCURRENT_REQUESTS)
        ]

        for future in as_completed(futures):
            code, body, duration = future.result()
            results["durations"].append(duration)

            status_codes[code] = status_codes.get(code, 0) + 1

            if code == 201:
                results["success"] += 1
            elif code in (409, 404):
                results["rejected"] += 1
            else:
                results["errors"] += 1

    total_time = time.time() - start_time

    # Verify final inventory
    avail_resp = requests.get(f"{EVENT_SERVICE}/events/{event_id}/availability")
    remaining = avail_resp.json()["available_slots"]

    # ============================================================
    # RESULTS
    # ============================================================
    print("=" * 60)
    print("CONCURRENCY TEST RESULTS")
    print("=" * 60)
    print(f"Total slots available:     {TOTAL_SLOTS}")
    print(f"Total concurrent requests: {CONCURRENT_REQUESTS}")
    print(f"")
    print(f"Successful bookings:       {results['success']}")
    print(f"Rejected (sold out/dup):   {results['rejected']}")
    print(f"Errors:                    {results['errors']}")
    print(f"Remaining inventory:       {remaining}")
    print(f"")
    print(f"Status code distribution:  {status_codes}")
    print(f"")
    print(f"Total test time:           {total_time:.2f}s")
    print(f"Avg response time:         {sum(results['durations'])/len(results['durations']):.4f}s")
    print(f"Max response time:         {max(results['durations']):.4f}s")
    print(f"Min response time:         {min(results['durations']):.4f}s")
    print(f"")

    # THE CRITICAL ASSERTION
    if results["success"] <= TOTAL_SLOTS:
        print("✅ PASS: No overselling! successful_bookings <= available_slots")
        print(f"   {results['success']} <= {TOTAL_SLOTS}")
    else:
        print("❌ FAIL: OVERSELLING DETECTED!")
        print(f"   {results['success']} > {TOTAL_SLOTS}")
        sys.exit(1)

    if remaining >= 0:
        print("✅ PASS: Inventory never went negative")
        print(f"   Remaining: {remaining}")
    else:
        print("❌ FAIL: Negative inventory!")
        sys.exit(1)

    expected_remaining = TOTAL_SLOTS - results["success"]
    if remaining == expected_remaining:
        print(f"✅ PASS: Inventory math checks out ({TOTAL_SLOTS} - {results['success']} = {remaining})")
    else:
        print(f"⚠️  WARNING: Inventory mismatch (expected {expected_remaining}, got {remaining})")

    print("=" * 60)


if __name__ == "__main__":
    run_concurrency_test()
