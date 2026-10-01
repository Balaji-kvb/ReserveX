import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const BOOKING_URL = __ENV.BOOKING_URL || 'http://localhost:5003';
const USER_URL = __ENV.USER_URL || 'http://localhost:5001';
const EVENT_URL = __ENV.EVENT_URL || 'http://localhost:5002';

const successfulBookings = new Counter('booking_successes');
const soldOutBookings = new Counter('booking_sold_out');
const unexpectedResponses = new Counter('booking_unexpected');
const bookingAttempts = new Counter('booking_attempts');

export const options = {
  setupTimeout: '2m',

  scenarios: {
    concurrency_test: {
      executor: 'per-vu-iterations',

      // 200 VUs = 200 real users in this experiment.
      vus: 200,

      // Each VU makes exactly ONE booking attempt.
      iterations: 1,

      maxDuration: '2m',
    },
  },

  thresholds: {
    booking_attempts: ['count==200'],
    booking_successes: ['count==50'],
    booking_sold_out: ['count==150'],
    booking_unexpected: ['count==0'],
  },
};

export function setup() {
  console.log('Creating ReserveX concurrency-test event...');

  // Create one event with exactly 50 slots.
  const eventResponse = http.post(
    `${EVENT_URL}/events`,
    JSON.stringify({
      name: `Concurrency Test ${Date.now()}`,
      total_slots: 50,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  check(eventResponse, {
    'event created': (r) => r.status === 201,
  });

  if (eventResponse.status !== 201) {
    throw new Error(
      `Could not create test event. Status=${eventResponse.status} Body=${eventResponse.body}`
    );
  }

  const event = eventResponse.json();

  console.log(`TEST EVENT ID: ${event.id}`);
  console.log(`TEST EVENT SLOTS: ${event.total_slots}`);

  // Create 200 real users.
  const userIds = [];

  for (let i = 1; i <= 200; i++) {
    const response = http.post(
      `${USER_URL}/users`,
      JSON.stringify({
        name: `Load User ${i}`,
        email: `load-${Date.now()}-${i}@reservex.local`,
      }),
      {
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    if (response.status !== 201) {
      throw new Error(
        `Could not create test user ${i}. Status=${response.status} Body=${response.body}`
      );
    }

    userIds.push(response.json().id);
  }

  console.log(`CREATED TEST USERS: ${userIds.length}`);

  return {
    eventId: event.id,
    userIds,
  };
}

export default function (data) {
  // __VU starts at 1.
  // Each VU gets exactly one unique user.
  const userId = data.userIds[__VU - 1];

  const response = http.post(
    `${BOOKING_URL}/bookings`,
    JSON.stringify({
      user_id: userId,
      event_id: data.eventId,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  bookingAttempts.add(1);

  check(response, {
    'booking returned expected status': (r) =>
      r.status === 201 || r.status === 409,
  });

  if (response.status === 201) {
    successfulBookings.add(1);
  } else if (response.status === 409) {
    soldOutBookings.add(1);
  } else {
    unexpectedResponses.add(1);

    console.log(
      `UNEXPECTED RESPONSE: status=${response.status} body=${response.body}`
    );
  }
}
