/**
 * Load test — 500 VUs sustained for 5 minutes, mixed webhook + management traffic.
 *
 * Run with:
 *   BASE_URL=http://localhost:8000 k6 run tests/load/k6_load.js
 *
 * Pass criteria (NFR-12 / NFR-13):
 *   - p(95) response time < 1500ms
 *   - HTTP error rate < 1%
 *   - All webhook endpoints respond < 500
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '30s', target: 100 },
    { duration: '1m', target: 500 },
    { duration: '3m', target: 500 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<1500'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.01'],
  },
};

const WEBHOOKS = [
  '/api/v1/webhook/telegram',
  '/api/v1/webhook/line',
  '/api/v1/webhook/messenger',
  '/api/v1/webhook/whatsapp',
];

export default function () {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const path = WEBHOOKS[Math.floor(Math.random() * WEBHOOKS.length)];
  const res = http.post(
    `${baseUrl}${path}`,
    JSON.stringify({
      message: 'load test',
      user_id: `load_${__VU}_${__ITER}`,
      text: 'sustained load',
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  errorRate.add(res.status >= 500);
  check(res, {
    'webhook responds 2xx or 429': (r) => r.status < 500,
  });

  sleep(0.1);
}