# Admin Cost & Agent-Health Dashboard

Internal-only page at `/admin/cost` that rolls up the per-user data we
already collect (`agent_runs`, `agent_cost_events`,
`production_test_runs`) into the cross-user views the original spec
asks for: cost over time, top spend by user / agent / model, burn
rate and month projection, expensive runs, recent agent runs, and
production-test health.

Phase 2c of the agentic-automation roadmap.

## What's in

- New permission `admin.cost.read` in `ADMIN_PERMISSIONS`
  ([`backend/app/security/permissions.py`](../backend/app/security/permissions.py)).
- Service [`backend/app/services/admin_cost_service.py`](../backend/app/services/admin_cost_service.py)
  with three public functions:
  - `build_admin_cost_overview(db, window_days=None)` — one-shot
    payload powering the dashboard.
  - `list_recent_runs_cross_user(db, limit, agent_kind?, status?)` —
    paginated agent_runs across all users.
  - `build_production_test_health(db, hours)` — proxies
    `production_test_service.get_failure_stats`.
- GraphQL surface (`admin.cost.read` permission):
  - `adminCostOverview(windowDays: Int)`
  - `adminAgentRuns(limit: Int, agentKind: String, status: String)`
  - `adminProductionTestStats(hours: Int)`
- Frontend page
  [`/admin/cost`](../frontend/src/features/admin/components/AdminCostDashboardPage.tsx)
  showing totals, burn + projection, daily spend chart, by-agent +
  by-model breakdowns, top users, expensive runs, recent runs with
  status filter, production-test card.

## What's NOT in (yet)

- **No alerting.** Just surfacing. PagerDuty / Slack hooks land
  later.
- **No cost-anomaly detection.** Use the `expensive_runs` view +
  daily series as the current signal.
- **No CSV export.** Read-only tables only.
- **No materialized rollup.** Aggregation is in-Python over raw
  `agent_cost_events`. EVENT_SCAN_CAP=50k; move to a rollup table
  if/when we cross that.

## Burn-rate + projection formulas

```
burn_rate_per_day_usd  = sum(billable in last 7 calendar days) / 7
month_to_date_billable = sum(billable since first of month)
projected_month        = month_to_date + burn_rate × days_remaining
```

## Tests

[`backend/tests/test_admin_cost_service.py`](../backend/tests/test_admin_cost_service.py)
covers: empty-repo shape, per-user/per-agent/per-model roll-ups, sort
order, failed-run counter, burn-rate math, month projection bound,
expensive-runs thresholding + top-10 fallback, window clamping,
cross-user runs with status + kind filters, production-test stats
proxy.
