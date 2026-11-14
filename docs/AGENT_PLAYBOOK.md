# Manifest Agent Playbook

Last verified against code on **May 1, 2026**.

This document is the operational guide for any human or AI agent contributing to this repository.

## 1. Core System Model

Manifest is a full-stack platform with four main execution paths:

1. GraphQL app API (`/graphql`) for most product features
2. REST APIs for specific capabilities (`/api/v1`, `/api/voice-agent`, `/api/keys`)
3. Internal feedback loops (`/api/internal/website-testing`, `/api/internal/survey-ops`, `/api/internal/production-signals`, MCP tools, GitHub workflows)
4. Background document-generation pipeline triggered by GraphQL `runBackgroundTasks`

## 2. Ownership Map (Where To Change What)

### Backend bootstrap and routing

- App bootstrap and middleware: `backend/app/main.py`
- GraphQL contract and resolvers: `backend/app/graphql/schema.py`
- REST routes: `backend/app/routes/*.py`
- Shared route auth dependency: `backend/app/routes/dependencies.py`
- Website audit and GitHub issue sync: `backend/app/routes/website_testing_routes.py`, `backend/app/services/operations/website_issue_sync.py`
- Survey analytics and GitHub triage: `backend/app/routes/survey_ops_routes.py`, `backend/app/services/operations/survey_ops.py`, `backend/app/services/integrations/github_issues.py`

### Backend orchestration and AI

- Primary orchestrator in production path: `backend/app/managers/manifest_manager.py`
- AI abstraction:
  - `backend/app/services/ai/layer.py`
  - `backend/app/services/ai/router.py`

### Business/document services

- Idea core: `backend/app/services/ideas/service.py`
- BMC: `backend/app/services/canvas/business_model_canvas.py`
- Similar ideas: `backend/app/services/ideas/similar_ideas.py`
- Pitch deck: `backend/app/services/documents/pitch_deck.py`
- PRD: `backend/app/services/documents/product_requirements_document.py`
- Patent draft: `backend/app/services/documents/provisional_patent.py`
- Idea qualification (pre-build conversational agent): `backend/app/services/ai/idea_qualification.py` + prompt `backend/app/prompts/idea_qualification.mcp.json` + table `idea_qualification_sessions`. Frontend page: `frontend/src/features/ideas/components/IdeaQualificationPage.tsx`. See `docs/IDEA_QUALIFICATION_AGENT.md`.
- Agent run + cost tracking: `backend/app/services/ai/cost_tracking.py` + `backend/app/services/ai/usage_tap.py` (router-to-tracker shim) + tables `agent_runs`, `agent_tasks`, `agent_cost_events`, `user_cost_limits`. Frontend billing page: `frontend/src/features/account/components/BillingDashboardPage.tsx`. AIRouter writes per-call usage into the tap; the cost service reads + persists. See `docs/COST_TRACKING.md`.

### Data and auth foundations

- Database client + in-memory fallback: `backend/app/db/database.py`
- Auth token parsing + demo mode: `backend/app/auth/current_user.py`
- Replit OAuth/session flow: `backend/app/auth/replit_auth.py`, `backend/app/routes/auth_routes.py`

### Frontend app shell and state

- App routes + view mode split: `frontend/src/App.tsx`
- GraphQL/Apollo client: `frontend/src/features/core/apollo/client.ts`
- GraphQL operations used by UI: `frontend/src/features/core/apollo/queries.ts`
- Reactive local state (`makeVar`): `frontend/src/features/core/apollo/localState.ts`

### Frontend feature modules

- Ideas editor/listing: `frontend/src/features/ideas/components/*`
- Discover/social feed: `frontend/src/features/discover/*`, `frontend/src/features/social/components/*`
- Account/integrations/API access: `frontend/src/features/account/components/*`
- Voice UX: `frontend/src/features/voice/*` (shared REST client: `frontend/src/features/voice/voiceAgentApi.ts`)
- Messaging/collaboration UI: `frontend/src/features/messaging/*`, `frontend/src/features/collaboration/*`

## 3. Agent Routing Matrix

Use this to dispatch tasks quickly.

- "Add or modify product data fields" -> `backend/app/graphql/schema.py` + frontend `queries.ts` + consuming components
- "Fix login/session behavior" -> `backend/app/auth/current_user.py`, `backend/app/graphql/schema.py` auth mutations, `frontend/src/features/auth/*`
- "Improve AI output quality" -> prompt JSON files in `backend/app/prompts/*.mcp.json` + `ai/layer.py`
- "Document generation bugs" -> `manifest_manager.py`, `idea_utils.py`, target document service
- "Public API key behavior" -> `backend/app/routes/api_v1_routes.py`, `backend/app/services/identity/api_keys.py`
- "Internal website audit / GitHub issue sync" -> `backend/app/routes/website_testing_routes.py`, `backend/app/services/operations/website_issue_sync.py`, `backend/scripts/run_website_issue_sync.py`, `.github/workflows/website-testing.yml`, MCP server files
- "Internal survey insights / GitHub triage" -> `backend/app/routes/survey_ops_routes.py`, `backend/app/services/operations/survey_ops.py`, `backend/app/services/integrations/github_issues.py`, `backend/scripts/run_survey_issue_sync.py`, `.github/workflows/survey-feedback.yml`, MCP server files
- "Voice agent issues" -> `backend/app/routes/voice_agent_routes.py`, `backend/app/services/voice/agent.py`, frontend voice components
- "Collaboration/messaging" -> GraphQL schema + `ideas/collaboration.py` or `social/messaging.py` + frontend feature components

## 4. High-Impact Workflows

### A) Add a new generated document type

1. Add/extend backend service under `backend/app/services/`.
2. Register in `backend/app/managers/manifest_manager.py`.
3. Add GraphQL resolver(s) in `backend/app/graphql/schema.py`.
4. If background-generated, integrate in `backend/app/services/ideas/document_generation.py`.
5. Add frontend GraphQL operation in `frontend/src/features/core/apollo/queries.ts`.
6. Add UI surface in ideas display components.
7. Add backend tests and frontend rendering tests.

### B) Add a new GraphQL field used by UI

1. Update Strawberry types and resolver return mapping in `backend/app/graphql/schema.py`.
2. Update query or mutation in `frontend/src/features/core/apollo/queries.ts`.
3. Update consuming component typings and render logic.
4. Run GraphQL-focused backend tests and affected frontend tests.

### C) Add a new REST endpoint

1. Implement route module in `backend/app/routes/`.
2. Include router in `backend/app/main.py`.
3. Add auth dependency if needed.
4. Add request/response model docs in `docs/API.md`.
5. Add route tests.

### D) Run the production website audit from an agent or workflow

1. Use `POST /api/internal/website-testing/sync-issues` when you are inside the trusted agent loop and can send `X-Manifest-Agent-Key`.
2. Use `audit_website_and_create_github_issues` from the MCP server when working from an external agent with the same internal secret.
3. Use `.github/workflows/website-testing.yml` for scheduled or manual repository-native runs.
4. Keep the shared behavior in `backend/app/services/operations/website_issue_sync.py`; do not fork the audit logic.

### E) Run the survey feedback loop from an agent or workflow

1. Use `POST /api/internal/survey-ops/summary` for aggregate marketability / PMF analysis.
2. Use `POST /api/internal/survey-ops/sync-issues` when recurring survey themes should become GitHub issues.
3. Use `summarize_survey_feedback` or `create_survey_feedback_github_issues` from the MCP server when working from an external agent.
4. Use `POST /api/internal/production-signals/event` (or MCP `emit_production_signal`) for deduped production anomaly signals; see `docs/PRODUCTION_SIGNALS_OPS.md`.
5. Use `.github/workflows/survey-feedback.yml` for scheduled or manual repository-native runs.
6. Keep issue creation shared through `backend/app/services/integrations/github_issues.py`; do not duplicate label or de-duplication logic.

## 5. Non-Obvious Constraints and Pitfalls

- `main.py` uses a singleton `ManifestManager`; background document generation serializes access with `_manifest_manager_lock` in `backend/app/services/ideas/document_generation.py`.
- `updateIdea` GraphQL mutation rejects empty/meaningless HTML description updates (intentional guardrail).
- `runBackgroundTasks` mutation returns immediately; document generation is asynchronous.
- Without `DATABASE_URL`, backend may run with in-memory DB and demo auth behavior.
- `/api/v1/ideas/{idea_id}/generate` runs synchronously in the request path; keep prompt size and timeout behavior in mind.
- Website issue sync is internal-only and requires `MANIFEST_AGENT_LOOP_SECRET` (or `AGENT_LOOP_SECRET`) plus backend GitHub credentials (`MANIFEST_GITHUB_TOKEN` or `GITHUB_TOKEN`) and repo configuration.
- Survey feedback automation uses the same internal secret and GitHub credential pattern, and also requires a real `DATABASE_URL` because `survey_responses` live in Postgres.
- Production signals require `DATABASE_URL` and the `production_signal_state` migration; GitHub issue creation is opt-in per request and uses the same token/repo env vars as other internal loops.

## 6. Quality Gate Before Merging

- Backend tests for changed domains pass.
- Frontend tests for changed domains pass.
- Docs updated for any API or workflow changes.
- No stale references to removed Redux slices (current state path is Apollo reactive vars).
- No claim in docs that conflicts with `backend/app/main.py` or `backend/app/graphql/schema.py`.
