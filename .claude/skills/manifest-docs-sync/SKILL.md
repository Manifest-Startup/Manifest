---
name: manifest-docs-sync
description: When a public Manifest contract changes, demand a matching `docs/` edit before the PR is allowed to land. Use whenever a change touches GraphQL schema, REST routes, MCP server contracts, environment variables, or the developer CLI surface. Refuses to mark the task done until the relevant doc file is updated in the same change.
---

# Manifest Docs Sync

`docs/CONTRIBUTING_AGENTS.md` lists *"docs reflect behavior"* as part of the definition of
done. In practice, public-contract changes ship without doc updates because the failure is
silent — tests still pass. This skill makes the failure loud.

## When to apply

Apply this skill whenever Edit/Write/MultiEdit touches any of:

- `backend/app/graphql/**` — GraphQL queries, mutations, types
- `backend/app/routes/**` — REST endpoints
- `backend/app/main.py` — top-level routing or middleware
- `mcp_server/**` — MCP tool definitions or schemas
- `.env.example` — environment variables (the canonical contract for ops)
- `src/manifest_dev/**` — developer CLI subcommands
- `frontend/src/api/**` — API client (a sign that the contract above changed)

## What to produce in the same change

| Surface changed | Doc to update |
| --- | --- |
| GraphQL query/mutation/type | `docs/API.md` (or `docs/GRAPHQL.md` if separate) |
| REST endpoint | `docs/API.md` |
| MCP tool | `mcp_server/README.md` and `docs/MCP.md` if present |
| Env var | `.env.example` (kept in lockstep) and `docs/CONFIGURATION.md` |
| Developer CLI | `src/manifest_dev/README.md` and `docs/DEVELOPER_CLI.md` if present |

If a relevant doc file does not exist yet, create it. Do not silently skip the doc update
because the file is missing.

## What "updated" means

- The doc reflects the *current* contract, not the previous one.
- Any deprecated endpoint or env var is marked deprecated with a removal date in the same
  PR.
- A short example (one curl, one GraphQL query, or one CLI invocation) is included for new
  surfaces.

## Why this matters

Manifest exposes a GraphQL API, a REST API, an MCP server, and a developer CLI. Each is
consumed by different humans and agents. Drift between code and docs is the fastest way to
break investor integrations, internal tooling, and the MCP bridge. Catching drift in the
PR is an order of magnitude cheaper than catching it in production support.
