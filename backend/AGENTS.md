# Backend — agent guide (child of [`../AGENTS.md`](../AGENTS.md))

FastAPI app with a Strawberry GraphQL API. Entry point `app/main.py` (mounts routers and `/graphql`). Python ≥ 3.11; imports are rooted at `backend/` (`from app.services.x import Y`).

## Layout (parent → child)

| Package | Responsibility | Depends on |
|---|---|---|
| `app/routes/` | REST routers (`*_routes.py`); thin: validate, authorise, call a service | services, security |
| `app/graphql/` | `schema.py` = every Query/Mutation resolver + `_DefaultDenyAuthExtension` (new fields are authenticated unless added to `PUBLIC_FIELDS`); `*_types.py` = Strawberry types | services, security |
| `app/services/` | Business logic, one concern per `*_service.py`; AI calls go through `ai_router.py` / `ai_layer_service.py` with cost tracking; the OpenAI key is the customer's own, resolved per request by `ai_credentials.py` (background threads: `start_thread_with_current_key`) | db, utils |
| `app/managers/manifest_manager.py` | Orchestrates document generation across services | services |
| `app/security/` | Auth policy, cookies (`cookies.py`), SSRF-safe HTTP (`safe_http.py`), audit chain, rate limits, crypto | config only |
| `app/auth/` | Session tokens (`replit_auth.create_session_token`) and identity helpers | security, db |
| `app/db/` | `database.py` (`get_db_connection`, Supabase client), `async_pool.py`, `rows.py` (row → JSON dicts) | — |
| `app/workers/` | Optional out-of-process job worker (`python -m app.workers.generation_worker`) | services |
| `app/utils/` | Logger, shared descriptors (`auto_property.py`), small helpers | — |

Dependencies point downward. Routes and resolvers never talk to the DB directly; services never import routes or `graphql/`. Known cycles to untangle rather than extend: `python3 ../scripts/codegraph/query.py cycles`.

## Working here

- Find the resolver or route first: `query.py graphql <field>` / `query.py routes <path>`, then `outline` the service it calls.
- Add a GraphQL field with the `manifest-graphql-resolver-template` skill; keep the resolver thin and put logic in a service.
- Set auth cookies only through `app/security/cookies.set_auth_cookies` / `secure_cookies_enabled`; outbound HTTP to user-supplied URLs only through `app/security/safe_http`.
- Schema changes: add a timestamped SQL file in `../supabase/migrations/`; never apply it unless asked.
- `scripts/` holds operator and CI scripts (Autopilot, security autofix); they may import `app.*` and are not part of the lint gate.

## Checks

```bash
cd backend && ../.venv/bin/python -m pytest -q -o addopts=""        # full suite (~30 s)
../.venv/bin/python -m pytest -q -o addopts="" tests -k <area>      # focused
python3 ../scripts/check.py --only python backend   # same checks, from the repo root
```

`pytest.ini` adds coverage reports by default; `-o addopts=""` skips them for fast local runs.
