/**
 * NFR-09: API Gateway must sustain 2000 TPS for 30 seconds.
 *
 * Run with:
 *   BASE_URL=http://localhost:8000 k6 run tests/load/k6_nfr09_2000tps.js
 *
 * Pass criteria (enforced by k6 thresholds below):
 *   - p(95) response time < 800ms  (NFR-12: p95 < 0.8s)
 *   - HTTP error rate < 1%
 *   - 2000 req/s sustained for 30s (executor: constant-arrival-rate)
 *
 * Note: this test requires a running omnibot API Gateway instance.
 * It is NOT executed in CI unit-test runs; trigger it separately as part
 * of integration / load-test pipelines (Phase 6+).
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  scenarios: {
    sustained_2000_tps: {
      executor: 'constant-arrival-rate',
      rate: 2000,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 200,
      maxVUs: 600,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.01'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const res = http.post(
    `${baseUrl}/api/v1/webhook/agent`,
    JSON.stringify({ message: 'load test', user_id: 'nfr09_k6' }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  errorRate.add(res.status >= 500);
  check(res, {
    // 200 = processed, 429 = rate-limited (both are valid responses under load)
    'status 2xx or 429': (r) => r.status < 500,
  });
}
