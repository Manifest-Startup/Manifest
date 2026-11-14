# Cost Tracking & Billing Foundation

The persistence layer + service + dashboard that every Manifest agent
hooks into to report what it spent. Phase 2 of the agentic-automation
roadmap; built directly on top of the qualification agent so the wiring
has a real-world caller from day one.

## What's in (Phase 2a)

- `agent_runs` — one row per agent execution with rolling token and cost
  totals
- `agent_tasks` — optional sub-steps inside a run (used once we fan out
  per-section BMC agents)
- `agent_cost_events` — one row per billable LLM/external call; the
  authoritative source of truth that the run totals are derived from
- `user_cost_limits` — per-user monthly variable cap, paused flag, base
  subscription. Lazily created with sensible defaults on first read.
- `cost_tracking_service` — the only module other services should
  import. Lifecycle (`start_agent_run` / `complete_agent_run`), cost
  ingest (`log_cost_event`, `log_cost_event_from_tap`), dashboard
  payload (`build_user_cost_dashboard`).
- `llm_usage_tap` — a tiny contextvar-backed helper. The AI router
  writes the latest call's usage into it; the cost service reads + pops
  the value immediately afterwards. Decouples the router from the
  billing layer.
- GraphQL surface: `myCostDashboard`, `myAgentRuns`, `setVariableCostCap`
- Frontend dashboard at `/account/billing`: subscription summary,
  variable-usage progress bar with 50/80/100% warning levels, per-agent
  + per-model breakdown, recent-runs table, cap controls (raise/lower,
  pause/resume).
- The qualification agent is wired in. Each session opens one
  `agent_runs` row; each turn that calls the LLM logs one
  `agent_cost_events` row; the run is marked `complete` when the
  session completes.

## What's deliberately NOT in (yet)

- **Enforcement.** The cap is displayed but not enforced server-side.
  A future slice will add `cost_tracking_service.guard_can_run()` and
  call it from each agent's entry point. Warnings cover the user-side
  feedback in the meantime.
- **Retrofit of BMC, pitch-deck, PRD, patent.** These still run
  un-tracked. They share the same AI layer, so retrofit is mostly:
  open a run, then add `log_cost_event_from_tap` next to each
  `generate_rich_text` call. Tracked as its own follow-up to keep
  blast radius small.
- **Admin dashboard.** Aggregated per-user / per-agent / anomaly views
  for internal ops. Backend already has the data; needs a separate
  permission scope and UI.
- **Pre-run cost estimates.** Showing "this is going to cost ~$X
  before you click run." Needs a separate token-counting helper +
  per-agent average-cost calibration.

## Pricing

Per-model rates live in
[`backend/app/services/ai/cost_tracking.py`](../backend/app/services/ai/cost_tracking.py)
under `PRICING_USD_PER_1M`. Unknown models fall back to a conservative
$1.00 / $3.00 per 1M tokens — chosen to err on the side of slight
over-billing rather than silent $0 events.

When OpenAI changes prices or we adopt a new model:

1. Update the dict literal. Include the version-pinned alias too (e.g.
   both `gpt-4o-mini` and `gpt-4o-mini-2024-07-18`).
2. Bump the doc date below.
3. Verify with `python -m pytest backend/tests/test_cost_tracking.py`.

Prices verified against OpenAI public pricing on **2026-05-20**.

The user-facing billable amount = model cost × `MANIFEST_BILLABLE_MARKUP_FACTOR`
(default 1.5x). The markup is never displayed; only the billable USD
is. The model cost is internal and stored separately on the same
event row so finance can reconcile.

## How a new agent plugs in

```python
from app.services.ai import cost_tracking as cts
from app.services.ai.usage_tap import pop_last_usage  # for inspection only

def run_my_new_agent(*, db, user_id, ai_layer, ...):
    run_id = cts.start_agent_run(
        db=db, user_id=user_id, agent_kind="my_new_agent",
    )
    try:
        # ... do work, including LLM calls via ai_layer ...
        result = ai_layer.generate_rich_text(messages)
        cts.log_cost_event_from_tap(
            db=db, user_id=user_id, agent_kind="my_new_agent",
            run_id=run_id, note="step 1",
        )
        # ... more LLM calls? log one event per call ...
        cts.complete_agent_run(db=db, run_id=run_id, status="complete")
        return result
    except Exception as exc:
        cts.fail_agent_run(db=db, run_id=run_id, error_message=str(exc))
        raise
```

Three rules:

1. **One run = one agent execution.** Not one LLM call. If a BMC
   regeneration calls the LLM nine times, that's one run with nine
   events.
2. **Never let cost logging break the user request.** Every cost path
   in `cost_tracking_service` swallows its own DB errors and logs at
   `WARNING`. The canonical totals can always be reconstructed from
   `agent_cost_events`.
3. **Use `log_cost_event_from_tap` right after the LLM call** — the
   tap is a contextvar; if too much code runs in between, an
   intervening LLM call could overwrite it.

## Schema cheat sheet

| Table | Owns | Hot indexes |
|---|---|---|
| `agent_runs` | run lifecycle + rolling totals | `(user_id, started_at DESC)`, `(agent_kind, started_at DESC)`, `(qualification_session_id)` partial |
| `agent_tasks` | optional fan-out under a run | `(run_id)` |
| `agent_cost_events` | billable per-call ground truth | `(user_id, created_at DESC)`, `(run_id)`, `(agent_kind, created_at DESC)` |
| `user_cost_limits` | per-user cap + pause + base sub | PK on `user_id` |

Migration:
[`supabase/migrations/20260520180000_agent_runs_cost_tracking.sql`](../supabase/migrations/20260520180000_agent_runs_cost_tracking.sql).

## GraphQL

Defined in [`backend/app/graphql/schema.py`](../backend/app/graphql/schema.py).
All under the default-deny extension's `account.read` / `account.write`
permissions:

| Operation | Permission |
| --- | --- |
| `myCostDashboard` | `account.read` |
| `myAgentRuns(limit: Int)` | `account.read` |
| `setVariableCostCap(monthlyCapUsd: Float, paused: Boolean)` | `account.write` |

`myCostDashboard` returns the full payload the billing page needs in one
round-trip: limits, monthly spend with by-kind + by-model breakdowns,
remaining $, % of cap, warning level (`ok` / `elevated` / `critical` /
`over`), recent runs.

## Tests

[`backend/tests/test_cost_tracking.py`](../backend/tests/test_cost_tracking.py)
covers: pricing math (known model, cached input discount, unknown
fallback, negative-token clamp), run lifecycle (start/complete/fail,
invalid status rejection), cost ingest (single + aggregated events;
tap-based ingest with no-usage path), cap read/write (defaults, clamp,
ceiling, pause), dashboard aggregation (by-kind, by-model, warning
thresholds, owner isolation), and the qualification retrofit (run
opens, events log, run closes on completion).

## Server-side cap enforcement (Phase 5)

The cap is now **enforced**, not just displayed. Before any
user-facing agent entry point opens an `agent_run`, the resolver
calls `cost_tracking_service.enforce_cap_or_raise(...)`. If the user
is paused, already over their cap, or the per-kind cost estimate
would push them over, the resolver raises a user-visible error
instead of spending tokens.

Enforced surfaces (mutations):

- `startIdeaQualification`
- `continueIdeaQualification`
- `regenerateBmcSection` (one section)
- `regenerateAllBmcSections` (passes a 9× estimate so a full canvas
  regeneration is not let through when one section's estimate alone
  would be permitted)
- `runPartnerDiscovery`

NOT enforced (system/internal agents):

- Bug-fix agent (runs in GitHub Actions; no user_id attribution)
- Production-test ingest (CI-driven; no user_id)
- Website audit + survey ops (internal)

The block reasons (in order of precedence):

1. **`paused`** — `user_cost_limits.paused = true`. Wins over cap state
   because it's the more actionable signal for the operator: pause is
   intentional, over-cap is a hit on a soft budget. The UI surfaces an
   "Unpause" button.
2. **`over_cap`** — `monthly_usage_usd >= cap_usd`. User has already
   crossed their cap; new runs blocked. UI prompts to raise the cap.
3. **`would_exceed_cap`** — `monthly_usage_usd + estimate > cap_usd`.
   User is under cap but the next run would push them over. Same
   actionable UI as `over_cap`.

`cap_usd = 0` is treated as "no cap configured" (unbounded). Only
`paused` can block in that case.

### Pre-run cost estimates

[`ESTIMATED_COST_USD_PER_RUN`](../backend/app/services/ai/cost_tracking.py)
is the calibration table the guard uses to decide whether a run
would exceed cap. p50 values per agent kind. Unknown kinds fall back
to `DEFAULT_ESTIMATED_COST_USD_PER_RUN = $0.01`. When you add a new
agent kind, append an entry here so the guard doesn't over-block.

### `myCostPreflight` (GraphQL preview API)

The frontend can ask "would a new run for `agent_kind=X` succeed
right now?" via `query myCostPreflight(agentKind: String, estCostUsd:
Float)`. Returns the same payload as `guard_can_run`. Used by the
BillingDashboardPage's banner and (future) per-agent action buttons
that need to disable themselves when over cap.

Permission: `account.read`. The mutation layer ALSO enforces — the
preflight is purely a UX preview, not a substitute for the gate.

### Tests

[`backend/tests/test_cost_cap_enforcement.py`](../backend/tests/test_cost_cap_enforcement.py)
covers: fresh-user allow, per-kind estimate, unknown-kind fallback,
explicit override, paused → blocked, paused wins over cap-state,
over_cap, would_exceed_cap edge cases (lands-at-cap is allowed; goes
+0.001 over is blocked), cap=0 means unbounded, structured exception
fields, human-readable error messages.

## Future work

- **Pre-run cost estimates via `tiktoken`**: today the guard uses a
  static per-kind p50. A `tiktoken`-based estimate that also reads
  the actual message length would tighten the bound on long
  qualification conversations.
- **Cost-anomaly detection** (Phase 5 next slice): rolling z-score
  per `agent_kind` over `agent_cost_events`, surfaces in the admin
  dashboard.
- **Real-time cost updates**: Socket.IO push when an
  `agent_cost_events` row is inserted so the dashboard ticks live.
