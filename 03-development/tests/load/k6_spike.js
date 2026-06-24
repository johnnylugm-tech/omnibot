/**
 * Spike test — sudden burst from 10 to 1500 VUs to test burst handling.
 *
 * Run with:
 *   BASE_URL=http://localhost:8000 k6 run tests/load/k6_spike.js
 *
 * Pass criteria:
 *   - System recovers within 30s after spike
 *   - No permanent failures (5xx < 5%)
 *   - p(99) response time < 5000ms during spike
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '10s', target: 10 },
    { duration: '10s', target: 1500 },
    { duration: '30s', target: 1500 },
    { duration: '10s', target: 10 },
    { duration: '20s', target: 10 },
  ],
  thresholds: {
    http_req_duration: ['p(99)<5000'],
    http_req_failed: ['rate<0.05'],
    errors: ['rate<0.05'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const res = http.post(
    `${baseUrl}/api/v1/webhook/line`,
    JSON.stringify({
      events: [{ type: 'message', message: { text: 'spike' } }],
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  errorRate.add(res.status >= 500);
  check(res, {
    'spike response': (r) => r.status < 500,
  });
}