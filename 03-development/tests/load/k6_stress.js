/**
 * Stress test — ramps from 200 to 2000 VUs to identify breaking points.
 *
 * Run with:
 *   BASE_URL=http://localhost:8000 k6 run tests/load/k6_stress.js
 *
 * Pass criteria:
 *   - p(95) response time < 3000ms even at peak load
 *   - System does not crash (HTTP 5xx < 10%)
 *   - Graceful degradation (some 429s acceptable)
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '30s', target: 200 },
    { duration: '1m', target: 1000 },
    { duration: '1m', target: 2000 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.10'],
    errors: ['rate<0.10'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const res = http.post(
    `${baseUrl}/api/v1/webhook/telegram`,
    JSON.stringify({
      update_id: __ITER,
      message: { text: 'stress test', chat: { id: __VU } },
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  errorRate.add(res.status >= 500);
  check(res, {
    'no 5xx': (r) => r.status < 500,
  });
}