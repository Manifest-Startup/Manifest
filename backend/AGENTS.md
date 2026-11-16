# Backend — agent guide (child of [`../AGENTS.md`](../AGENTS.md))

FastAPI app with a Strawberry GraphQL API. Entry point `app/main.py` (mounts routers and `/graphql`). Python ≥ 3.11; imports are rooted at `backend/` (`from app.services.x import Y`).

## Layout (parent → child)

Dependencies only point **down** these layers; `tests/test_architecture.py` fails the build when a module reaches up.

| Layer | Packages | Responsibility |
|---|---|---|
| API | `app/routes/` (`*_routes.py`), `app/graphql/` (`schema.py`, `*_types.py`), `app/middleware/`, `app/workers/`, `app/main.py` | HTTP and jobs: validate, authorise, call a service. New GraphQL fields are authenticated unless listed in `PUBLIC_FIELDS`. |
| Services | `app/services/<domain>/`, `app/managers/`, `app/auth/`, `app/security/` | Business rules, grouped by domain (below). Never import routes, GraphQL or `app.main`. |
| Data | `app/db/` (`database.get_db_connection`, `rows.rows_to_dicts`) | Postgres/Supabase access. |
| Utils | `app/utils/` (logger, request context, descriptors), `app/prompts/` (`prompt_path`), `app/assets/` (`ASSETS_DIR`) | No knowledge of the app above them. |

Service domains (`app/services/<domain>/`, each `__init__.py` says what belongs there):
`ai` (router, credentials = the customer's own OpenAI key, usage and cost) · `canvas` (Business Model Canvas sections) · `documents` (generated legal and business documents) · `ideas` (ideas, versions, collaboration, generation jobs) · `pitch_reels` · `social` (follows, messaging, investments) · `voice` · `identity` (sessions, enterprise SSO, guests, API keys; sign-in itself is Open Media, ADR 0002) · `compliance` (consent, data-subject requests, retention, audit) · `integrations` (GitHub, Open Media, analytics) · `operations` (internal quality loops) · `web` (agent pages, SPA shell) · `shared` (cache, rate limit).

Module names say what the code is about, without suffixes: `services/documents/founders_agreement.py`, not `founders_agreement_service.py`. Shared objects live beside their class (`app.managers.manifest_manager.manifest_manager`), never in `app.main`. Logs are JSON with OpenTelemetry field names (`service.name`, `code.*`, `exception.*`, `request_id`); log through `app.utils.logger.logger` with `extra={...}` for structured fields.

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
