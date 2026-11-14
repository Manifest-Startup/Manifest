// Manifest performance smoke/load test (k6) — Phase 1 of the Performance
// Migration Strategy. Captures p50/p95/p99 against the SLO budgets so later
// phases can prove (not assume) they got faster, and so CI can fail a build
// that regresses a budget.
//
// Run locally (install k6: https://k6.io/docs/get-started/installation/):
//   BASE_URL=https://staging.manifeststartup.com \
//   GRAPHQL_URL=https://staging-api.manifeststartup.com/graphql \
//   k6 run loadtest/smoke.js
//
// CI gate (example): k6 run --quiet loadtest/smoke.js — non-zero exit if a
// threshold is breached. Point it at a *staging* deploy, never prod.
//
// Env:
//   BASE_URL      front-end origin to load (default localhost:3000)
//   GRAPHQL_URL   GraphQL endpoint (default ${BASE_URL}/graphql)
//   VUS, DURATION virtual users / duration (default 5 / 30s)

import http from "k6/http";
import { check, group } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:3000";
const GRAPHQL_URL = __ENV.GRAPHQL_URL || `${BASE_URL}/graphql`;

const pageLoad = new Trend("page_load_ms", true);
const cachedRead = new Trend("graphql_cached_read_ms", true);

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || "30s",
  // Budgets straight from the strategy doc (§0 "Verdict and targets").
  thresholds: {
    // Static/cached page paint proxy — TTFB+download of the shell.
    page_load_ms: ["p(95)<1000"],
    // Cached GraphQL reads — <150ms p95 at origin (edge target is <50ms).
    graphql_cached_read_ms: ["p(95)<400"], // origin-uncached ceiling; tighten to 150 once edge cache lands
    http_req_failed: ["rate<0.01"],
  },
};

// A cacheable, side-effect-free read. Adjust the query to a real cached
// resolver once persisted queries / edge cache (Phase 4) are in place.
const HEALTH_QUERY = JSON.stringify({ query: "query SmokeHealth { __typename }" });

export default function () {
  group("front-end shell", () => {
    const res = http.get(BASE_URL);
    pageLoad.add(res.timings.duration);
    check(res, {
      "shell 200": (r) => r.status === 200,
      "shell has #root": (r) => typeof r.body === "string" && r.body.includes('id="root"'),
    });
  });

  group("graphql cached read", () => {
    const res = http.post(GRAPHQL_URL, HEALTH_QUERY, {
      headers: { "Content-Type": "application/json" },
    });
    cachedRead.add(res.timings.duration);
    check(res, {
      "graphql 200": (r) => r.status === 200,
      "graphql no errors": (r) => {
        try {
          return !JSON.parse(r.body).errors;
        } catch (_e) {
          return false;
        }
      },
    });
  });
}
