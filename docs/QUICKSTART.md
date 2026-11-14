# Manifest Quick Start

Last verified against code on **May 1, 2026**.

## 1. Prerequisites

- Python 3.11+
- Node.js 18+
- npm
- (Optional) PostgreSQL/Supabase credentials for persistent data

## 2. Configure Environment

Create `.env` in the project root (`/Users/mihir/Projects/Manifest/.env`).

Minimum useful variables:

```env
# Required for production-safe auth
SESSION_SECRET=replace-with-a-strong-secret

# Optional: if missing, backend uses in-memory DB mode
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Optional: if missing, AI generation and voice AI are disabled
OPENAI_API_KEY=your_openai_api_key
AI_MODEL=gpt-4o-mini
VOICE_AGENT_MODEL=gpt-4o-mini
VOICE_AGENT_TTS_MODEL=tts-1
VOICE_AGENT_TTS_VOICE=nova
# Optional: near-instant speech-to-speech over WebRTC (off by default; costs more than tts-1)
VOICE_REALTIME_ENABLED=false
VOICE_REALTIME_MODEL=gpt-4o-realtime-preview
VOICE_REALTIME_VOICE=shimmer

# Optional analytics
POSTHOG_API_KEY=
REACT_APP_PUBLIC_POSTHOG_KEY=
REACT_APP_PUBLIC_POSTHOG_HOST=

# Optional frontend override; default is /graphql
REACT_APP_GRAPHQL_URL=
```

Important runtime behavior:

- Backend loads `.env` from project root in `backend/app/main.py`.
- If `DATABASE_URL` is missing, `DEMO_MODE` auto-enables and DB falls back to in-memory client.
- Demo login credentials default to:
  - Email: `hello@manifeststartup.com`
  - Password: `manifest`

## 3. Install Dependencies

```bash
cd /Users/mihir/Projects/Manifest
python3 -m pip install -e .
manifest-dev setup
```

## 4. Run the Stack

Use one of these methods.

### Method A: Start each service manually

```bash
# Terminal 1: backend
cd /Users/mihir/Projects/Manifest/backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: frontend
cd /Users/mihir/Projects/Manifest/frontend
npm start
```

### Method B: Scripted startup

```bash
cd /Users/mihir/Projects/Manifest
manifest-dev start
```

### Method C: Dev Container

Open the repository in VS Code or Cursor and choose **Reopen in Container**. The
dev container provisions Python 3.11, Node 20, backend dependencies, and frontend
packages automatically via `scripts/bootstrap.sh`.

## 5. Verify Services

- Frontend: `http://localhost:3000`
- Backend ping: `http://localhost:8000/ping`
- GraphQL endpoint: `http://localhost:8000/graphql`
- Public REST API root: `http://localhost:8000/api/v1/`
- Voice agent REST: `http://localhost:8000/api/voice-agent/start`
- Voice command catalog: `http://localhost:8000/api/voice-agent/capabilities`

## 6. Minimal API Smoke Test

```bash
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query { profile { userId email } }"}'
```

Expected behavior when not authenticated: `profile` resolves to `null`.

## 7. Test Commands

```bash
# backend tests
cd /Users/mihir/Projects/Manifest/backend
./run_tests.sh

# frontend tests
cd /Users/mihir/Projects/Manifest/frontend
npm test
```
