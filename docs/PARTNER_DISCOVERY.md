# Partner Discovery Agent

Given a startup idea, produces a ranked list of real-world partner
candidates a founder could integrate with for the MVP. Hooks directly
into the BMC `key_partners` section — the panel surfaces concrete
named vendors with integration metadata (api / mcp / sdk / webhook /
zapier / manual / unknown) instead of generic placeholders.

Phase 4 of the agentic-automation roadmap.

## What's in (v1, LLM-only)

- `partner_candidates` table
  ([migration](../supabase/migrations/20260523120000_partner_candidates.sql)):
  one row per (idea_id, name) with category, integration metadata,
  ranking, approval flag, agent_runs FK.
- Prompt template
  [`partner_discovery.mcp.json`](../backend/app/prompts/partner_discovery.mcp.json)
  with strict-JSON output and qualification + existing-key-partners
  threading.
- Service
  [`backend/app/services/partner_discovery_service.py`](../backend/app/services/partner_discovery_service.py):
  - `run_discovery` — one cost-tracked agent_run per call
    (`agent_kind = partner_discovery`), normalizes + ranks +
    upserts candidates.
  - `list_candidates` — ranked retrieval.
  - `approve_candidate` — internal approval flag, **no outreach**.
- GraphQL surface (gated by the default-deny extension under
  `ideas.read` / `ideas.write`):
  - `partnerCandidates(ideaId)` — ranked candidates for an owned idea.
  - `runPartnerDiscovery(ideaId, maxCandidates)` — run one discovery
    pass. Returns persisted candidates.
  - `approvePartnerCandidate(candidateId, approved)` — toggle the
    internal flag.
- Frontend panel
  [`PartnerCandidatesPanel.tsx`](../frontend/src/features/ideas/components/PartnerCandidatesPanel.tsx)
  rendering candidate cards with integration badges, relevance
  + confidence + difficulty + pricing fields, suggested use,
  recommended next step, risk notes, and an internal-only approve
  toggle.

## Safety boundary (CRITICAL)

Per the original spec ("Do not contact partners or send data
externally without user approval"), v1 explicitly avoids any external
action:

- The discovery agent calls **the LLM only** — no third-party APIs,
  no scraping, no contact forms.
- The "Approve" button flips `partner_candidates.approved` ONLY. It
  does NOT send email, does NOT call any partner's API, does NOT
  create rows in `integrations`, does NOT initiate any handshake.
- A future outreach agent (separate slice) will read
  `approved=true` rows and act ONLY with additional explicit user
  consent at that point.

If you change either of those properties in a future slice, update
this section AND the corresponding warning in
`PartnerCandidatesPanel.tsx`. The user-facing contract is "approve
is internal".

## Ranking + dedupe

The service normalizes the LLM output before persistence:

- Drops entries without `name` or `category`.
- Dedupes by lowercased name (so "Stripe", "stripe", and "STRIPE"
  collapse to the first occurrence).
- Clamps `integration_type` into the documented enum
  (`api / mcp / sdk / webhook / zapier / manual / unknown`); invalid
  values fall back to `unknown`.
- Clamps `relevance_score` into 0–100.
- Clamps `implementation_difficulty` and `confidence` to documented
  enums; invalid values become `null`.
- Sorts by `relevance_score` descending, breaks ties by name. Assigns
  `rank = 1, 2, 3, ...` in that order.

Re-running discovery on the same idea **updates** existing candidates
by name and reassigns rank — no duplicate rows. New candidates land
with a fresh UUID.

## Cost tracking

Every discovery pass opens one `agent_run` with `agent_kind =
partner_discovery`. The LLM call writes its token usage to
`llm_usage_tap`, and the service pops + logs it as one
`agent_cost_events` row. So a typical pass = 1 run + 1 event.

The billing dashboard at `/account/billing` and the admin dashboard
at `/admin/cost` pick this up automatically because both group by
`agent_kind`.

Cost ballpark for `gpt-4o-mini` (the default model): ~$0.001–$0.005
per pass for 8–12 candidates. The qualification summary + existing
BMC `key_partners` section get threaded into the prompt, which adds
some tokens but stays well under the user's monthly cap.

## Tests

[`backend/tests/test_partner_discovery_service.py`](../backend/tests/test_partner_discovery_service.py)
covers: idea-without-description rejection, unavailable AI layer
rejection, happy-path persistence + cost logging + run closure,
ranking by relevance_score, dropping entries without name/category,
clamping invalid integration_type / relevance_score / confidence /
difficulty, dedupe by lowercased name, re-run upsert (no dupes,
fields updated), approval flag round-trip, approval on missing
candidate, LLM-error → failed run, existing BMC `key_partners` text
threading into the prompt.

## What this enables next

- **Outreach agent (Phase 5+).** Reads `approved=true` rows, drafts
  outreach copy, surfaces it to the user as a comment-only preview.
  ANY outbound contact requires another explicit consent step.
- **Integration-plan generation.** For candidates with
  `integration_type in (api, mcp, sdk, webhook)`, generate a concrete
  "how to integrate this in 2 hours" plan. Cost-track as
  `agent_kind = partner_integration_plan`.
- **Web-grounded discovery.** Optional second strategy that uses the
  existing `perform_web_search_json` path in `ai_layer_service.py`
  so candidates are grounded in current public web data with
  citations. Higher cost (~$0.05/run); land as
  `groundWithWeb: true` arg on the mutation.
- **BMC `key_partners` auto-refresh.** When discovery completes, the
  BMC orchestrator could regenerate the `key_partners` section so
  the canvas summary reflects the new candidates.
