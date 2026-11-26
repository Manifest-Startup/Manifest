# Manifest Documentation

Last verified against code on **May 1, 2026**.

This folder contains the maintained documentation for the Manifest platform.

## Start Here

- [Quick Start](./QUICKSTART.md)
- [Product vision](./PRODUCT_VISION.md)
- [Short task prompt template (AI work)](./PROMPT_TEMPLATE.md)
- [API Reference](./API.md)
- [Manifest CLI](./CLI.md)
- [Architecture Reference](./ARCHITECTURE_REFERENCE.md)
- [Architecture decision records](./adr/README.md) (`adr/`)
- [Documentation license](./LICENSE.md) (CC BY 4.0) and the repository [NOTICE](../NOTICE)
- [Configuration](./CONFIGURATION.md)
- [Open Media integration](./OPEN_MEDIA_INTEGRATION_PLAN.md) and its [API contract](./OPEN_MEDIA_CONTRACT.md)
- [Partner connections](./PARTNER_CONNECTIONS.md): key partners, official sign-ins and the owner setup for each provider
- [Agent Playbook](./AGENT_PLAYBOOK.md)
- [Contributing Guide for Agents](./CONTRIBUTING_AGENTS.md)
- [Voice Agent API](./VOICE_AGENT_API.md)
- [Supabase Security Notes](./SUPABASE_SECURITY.md)
- [Migration from Replit](./MIGRATION_FROM_REPLIT.md)
- [Local dev without Replit](./LOCAL_DEV_WITHOUT_REPLIT.md)
- [Vercel deployment](./VERCEL_DEPLOYMENT.md)
- [Render deployment](./RENDER_DEPLOYMENT.md)
- [Database migration](./DATABASE_MIGRATION.md)
- [Parallel deploy checklist](./PARALLEL_DEPLOY_CHECKLIST.md)
- [Production readiness checklist](./PRODUCTION_READINESS_CHECKLIST.md)
- [DNS cutover and rollback](./DNS_CUTOVER_AND_ROLLBACK.md)
- [Performance migration notes](./PERFORMANCE_MIGRATION_NOTES.md)
- [Replit removal plan (future)](./REPLIT_REMOVAL_PLAN.md)
- [Founding memo (original vision, edited)](./FOUNDING_MEMO.md)

## What Is Source of Truth?

If docs and code ever disagree, treat the code as source of truth:

- Backend entrypoint: `backend/app/main.py`
- GraphQL schema: `backend/app/graphql/schema.py`
- Backend orchestrator: `backend/app/managers/manifest_manager.py`
- Frontend entrypoint: `frontend/src/App.tsx`

## Generated Artifacts

These are generated outputs, not hand-maintained docs:

- `docs/coverage/`
- `docs/backend-coverage/`
- `docs/performance/`
- `docs/test-report.html`

## Public API HTML

The static API page served by backend `/api/docs` lives at:

- `docs/public/api/index.html`
