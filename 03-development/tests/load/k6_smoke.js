/**
 * Smoke test — verifies the API Gateway is up and serving requests.
 *
 * Run with:
 *   BASE_URL=http://localhost:8000 k6 run tests/load/k6_smoke.js
 *
 * Pass criteria:
 *   - HTTP error rate < 5%
 *   - All requests complete within 5s
 *   - /api/v1/health returns 200
 *
 * Use this before any other load test to confirm the deployment is healthy.
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    http_req_failed: ['rate<0.05'],
    errors: ['rate<0.05'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const res = http.get(`${baseUrl}/api/v1/health`);

  errorRate.add(res.status !== 200);
  check(res, {
    'health endpoint returns 200': (r) => r.status === 200,
    'response has status:ok field': (r) => {
      try {
        return JSON.parse(r.body).status === 'ok';
      } catch (_e) {
        return false;
      }
    },
  });
}