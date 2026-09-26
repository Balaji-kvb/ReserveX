import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 },  // Ramp up to 50 virtual users
    { duration: '2m', target: 50 },   // Sustain 50 VUs
    { duration: '30s', target: 0 },   // Ramp down
  ],
};

// We will pass the base URL as an environment variable
const BASE_URL = __ENV.BASE_URL || 'http://localhost:5003';

export default function () {
  // 1. Health check (lightweight)
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, { 'health is 200': (r) => r.status === 200 });

  // 2. Metrics check (CPU intensive as prometheus library formats data)
  const metricsRes = http.get(`${BASE_URL}/metrics`);
  check(metricsRes, { 'metrics is 200': (r) => r.status === 200 });

  // Most will 404 on User Service if not seeded, but if we seed them, it will work.
  // We use __VU and __ITER to guarantee unique combinations for the constraint.
  const userId = (__VU * 10000) + __ITER;
  const eventId = (__ITER % 10) + 1; 

  const payload = JSON.stringify({
    user_id: userId,
    event_id: eventId,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const bookingRes = http.post(`${BASE_URL}/bookings`, payload, params);
  
  // We don't strictly check for 201 here because we know we're sending fake users
  // and some might conflict. We just want to generate CPU load on the service.

  // Sleep slightly to pace requests but keep CPU high
  sleep(0.1);
}
