# Idea Qualification Agent

The conversational pre-build agent that qualifies both the **user** and the
**idea** before Manifest spends LLM tokens generating a Business Model
Canvas, pitch deck, PRD, or patent draft.

This document describes Phase 1 of the wider agentic-automation roadmap.
The cost-tracking foundation, per-section BMC agents, partner-discovery
agent, and bug-fix PR agent are tracked separately and will be wired in
on top of the same primitives once they land.

## Why it exists

Manifest's existing document-generation pipeline runs to completion the
moment a user types an idea description, even if the idea is half-formed
or the user isn't actually ready to act on it. The qualification agent
turns the front door into a short, warm conversation:

- It extracts structured fields about the user (seriousness, domain
  knowledge, goals, budget, timeline, execution ability).
- It extracts structured fields about the idea (market need, target
  customer, feasibility, defensibility, revenue potential, competition,
  risks).
- It returns a 0–100 score with a 2–4 sentence explanation so the user
  can see how Manifest is reading the proposal.

When the user converts the session into an idea, the downstream
generation pipeline gets a richer starting context than it would have
from a description alone.

## Data model

Single table: `idea_qualification_sessions`
(migration: [`supabase/migrations/20260520120000_idea_qualification_sessions.sql`](../supabase/migrations/20260520120000_idea_qualification_sessions.sql)).

Per-session columns hold the 13 structured fields the agent tries to
populate, the score, the conversation transcript (`JSONB`), the current
`next_question`, a turn counter, and the status (`in_progress`,
`complete`, `abandoned`). The table is owned per-user — there is no
sharing model for sessions.

## Agent loop

One turn of the agent does two things:

1. **Extract.** Look at the latest user reply (in transcript context) and
   return any structured fields the agent can confidently infer from it.
   Never overwrites a field that's already locked in; only fills nulls.
2. **Decide.** Either ask the next best question targeting the highest-
   value unknown, or finish with a score + explanation.

Completion triggers when **either**:

- the LLM returns `decision = "complete"` (it has enough signal), or
- `turn_count` reaches `MAX_TURNS` (8). In that case the service falls
  back to averaging the populated 1–10 integer fields and scaling to
  0–100, so users always reach a terminal state.

The prompt template is loaded from
[`backend/app/prompts/idea_qualification.mcp.json`](../backend/app/prompts/idea_qualification.mcp.json).
Output is strict JSON; the service tolerates malformed responses by
falling back to a generic next question and continuing the session.

## GraphQL surface

Defined in [`backend/app/graphql/schema.py`](../backend/app/graphql/schema.py).
Permissions enforced by the `_DefaultDenyAuthExtension` and registered in
`FIELD_PERMISSIONS`:

| Operation | Permission |
| --- | --- |
| `startIdeaQualification(initialIdeaText)` | `ideas.write` |
| `continueIdeaQualification(sessionId, userMessage)` | `ideas.write` |
| `ideaQualificationSession(sessionId)` | `ideas.read` |
| `myIdeaQualificationSessions` | `ideas.read` |

All four resolvers go through `get_current_user_id`, and the service
layer scopes every DB read/write to the calling user — there is no path
that returns or mutates another user's session.

## Frontend

`/ideas/qualify` mounts
[`IdeaQualificationPage`](../frontend/src/features/ideas/components/IdeaQualificationPage.tsx).
It opens with a seed-text form, then becomes a chat view once the
session exists (URL is `?session=<id>` so reloads resume in place). On
completion the page shows the score, a plain-English band ("Strong",
"Promising", "Significant gaps", "Not yet ready"), the explanation, and
a single "Convert to an idea" CTA that calls `createIdea` with the
original idea text.

## Operational notes

- **Cost-tracked.** Each session opens an `agent_runs` row with
  `agent_kind='qualification'` linked via `qualification_session_id`.
  Every LLM-calling turn logs an `agent_cost_events` row via the
  `llm_usage_tap` (token counts come from the OpenAI response). The
  run is closed when the session completes. See
  [`docs/COST_TRACKING.md`](COST_TRACKING.md).
- **No background jobs** — every turn runs synchronously inside the
  GraphQL request. If the LLM call fails, the session stays
  `in_progress` and the user can retry. Persisted state is the source of
  truth.
- **No guest support yet** — qualification mutations are gated on
  `ideas.write`, which guest sessions hold; however the agent has not
  been hardened for the guest → authenticated merge flow. Treat guest
  qualification as best-effort until the merge path is updated.

## Tests

Backend coverage lives in
[`backend/tests/test_idea_qualification.py`](../backend/tests/test_idea_qualification.py)
and exercises: opening turn, field merge (nulls only, never overwrite),
LLM-driven completion, turn-cap completion with fallback score, owner
isolation, and graceful behavior when the AI layer is offline.

## What this enables next

The qualification session becomes the canonical input for downstream
agents. Once cost-tracking and `agent_runs` land, each BMC-section
generation can be modeled as an agent_run scoped to the qualification
session ID; the score, structured fields, and transcript will flow into
their prompts so the BMC has explicit, justified inputs rather than a
free-text description.
