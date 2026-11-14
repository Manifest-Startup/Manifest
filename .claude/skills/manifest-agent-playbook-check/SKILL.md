---
name: manifest-agent-playbook-check
description: Before editing a file in the Manifest repo, verify it is owned by the agent/module the task is about. Use when the assistant is about to call Edit/Write/MultiEdit on any file in `backend/`, `frontend/`, `mcp_server/`, or `supabase/` — especially for changes that span GraphQL, REST, services, and UI. Refuses edits to files that the canonical playbook assigns to a different agent unless the task explicitly mentions that surface.
---

# Manifest Agent Playbook Check

Manifest's architecture is described in `AGENTS.md` and `docs/CONTRIBUTING_AGENTS.md`. Edits
that touch the wrong module are the most common failure mode the contributing-agents doc
calls out (e.g. *"editing wrong module"*, *"overwriting descriptions with empty HTML"*,
*"triggering too many background tasks"*).

## When to apply

Apply this skill whenever you are about to make your first Edit/Write/MultiEdit in a
session that touches code under any of these roots:

- `backend/app/services/` — service layer
- `backend/app/graphql/` — Strawberry resolvers and schema
- `backend/app/routes/` — REST endpoints
- `backend/app/auth/`, `backend/app/security/` — auth and security
- `backend/app/prompts/` — AI prompts
- `frontend/src/features/<feature>/` — UI (shared primitives in `features/common-ui/`)
- `mcp_server/` — MCP bridge
- `supabase/migrations/` — schema migrations

## What to do

1. Re-read `AGENTS.md` — section "Agent architecture and flow" — and confirm the file you
   are about to touch belongs to the agent the task is about (ManifestManager, AI Layer,
   Service Layer, Frontend, Guest sessions, Pitch Reels, Founder messaging).
2. Re-read `docs/CONTRIBUTING_AGENTS.md` — section "Before coding" — and confirm GraphQL/
   REST/UI/service scope, async behaviour, and auth expectations.
3. If the change spans multiple agents, list them in the Plan and confirm each ownership
   point is intentional. Do not silently edit cross-cutting files.
4. If the file is *not* owned by the agent the task names, stop and ask the user: *"This
   edit lands in <module>, owned by <other agent>. Is that intentional?"*.
5. Once verified, proceed with the edit.

## Why this matters

Manifest changes that ripple across modules without owner-awareness break socket.io flows,
duplicate background tasks, or overwrite generated artifacts. The playbook check is a
30-second cost that saves hour-long incident loops downstream.
