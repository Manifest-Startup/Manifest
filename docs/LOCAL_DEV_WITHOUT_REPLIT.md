# Local development without Replit

Run Manifest on your machine using GitHub as the source of truth. No Replit account required.

## Prerequisites

- Python 3.11+ (backend Docker uses 3.13; local 3.11+ is fine)
- Node.js 20+ and npm
- Optional: PostgreSQL or Supabase `DATABASE_URL` for persistent data

## Quick start

From the repository root:

```bash
python3 -m pip install -e .
manifest-dev setup
manifest-dev start
```

Or use the scripts directly:

```bash
python3 scripts/setup_project.py
python3 scripts/start_app.py
```

**URLs**

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| GraphQL | http://localhost:8000/graphql |
| Health | http://localhost:8000/ping or `/health` |

## Environment

Copy the template and fill in values:

```bash
cp .env.example .env
```

**Demo mode (no database):** leave `DATABASE_URL` unset. The backend uses an in-memory database; AI features need `OPENAI_API_KEY`.

**Postgres:** set `DATABASE_URL=postgresql://user:pass@host:5432/dbname`.

**Auth:** set `SESSION_SECRET` to a long random string for non-demo login.

See [`.env.example`](../.env.example) for the full variable list.

## Frontend only

```bash
cd frontend
npm ci
npm start
```

Vite proxies `/graphql`, `/api`, `/auth`, and `/generated` to `http://localhost:8000` (see `frontend/vite.config.ts`).

## Backend only

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

## Dev container

Open the repo in VS Code or Cursor and use **Reopen in Container** if a devcontainer is configured.

## Differences from Replit

| Replit | Local / Vercel + Render |
|--------|-------------------------|
| Replit OIDC (`/auth/login`) | Email/password GraphQL auth |
| Replit Postgres env | Your `DATABASE_URL` or demo in-memory |
| Replit-managed secrets | `.env` locally; platform dashboards in prod |
| Single Replit URL | Frontend `:3000`, backend `:8000` (dev) |

Replit deployment is unchanged until you complete [MIGRATION_FROM_REPLIT.md](./MIGRATION_FROM_REPLIT.md).
