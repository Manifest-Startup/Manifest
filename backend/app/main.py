# NOTE: The backend loads the .env file from the project root (one level above 'backend'), not from the backend directory itself.
# Socket.IO is enabled and /socket.io/ will not 404 if uvicorn is used.
import os
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from threading import Thread

import socketio
from dotenv import load_dotenv

# Load .env before any app module that reads DATABASE_URL / demo mode at import time.
project_root = Path(__file__).resolve().parents[2]
env_path = project_root / ".env"
if not env_path.exists():
    env_path = Path.cwd() / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}", flush=True)
else:
    print(
        f"⚠️  .env not found at {env_path} — demo / in-memory mode is fine; add .env for Supabase, Postgres, and AI keys.",
        flush=True,
    )

from app.graphql.schema import schema
from app.middleware import RequestIDMiddleware
from app.middleware.metrics import setup_metrics
from app.routes.customer_routes import track_visitors_middleware
from app.security.config import frontend_origins_from_env
from app.security.security_headers import SecurityHeadersMiddleware
from app.services.ai.credentials import AIRequestContextMiddleware
from app.services.compliance.privacy_consent import (
    analytics_enabled_for_cookie_header,
    analytics_enabled_for_request,
)
from app.services.ideas.document_generation import generate_background_tasks
from app.services.integrations.analytics import capture_event
from app.services.web.spa_fallback import register_spa_fallback
from app.utils.logger import logger
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from socketio import ASGIApp
from strawberry.fastapi import GraphQLRouter

# Configure CORS origins based on environment.
# Closes SEC-001 — production no longer accepts the localhost regex; the
# loopback origins below are only injected when ENVIRONMENT is dev/test.
ENVIRONMENT = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "production").strip().lower()
_IS_NON_PROD = ENVIRONMENT in {"development", "dev", "test", "ci", "local"}


def _fastapi_docs_kwargs() -> dict[str, str | None]:
    """Disable framework Swagger/OpenAPI in production.

    Public product docs are served by the SPA routes. The raw FastAPI schema
    includes admin/internal endpoints and should only be available in
    non-production environments unless explicitly enabled for an internal run.
    """

    docs_enabled = _IS_NON_PROD or (
        os.getenv("ENABLE_INTERNAL_API_DOCS") or ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if docs_enabled:
        # /openapi.json is reserved for the curated public REST API spec.
        return {"openapi_url": "/internal/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


def _set_cache_control_headers(request: Request, response: Response) -> None:
    """Apply production cache policy for the SPA shell and fingerprinted assets."""

    path = request.url.path
    if path.startswith(("/assets/", "/static/")):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        return
    if path.startswith("/generated/pdfs/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
        return
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Cache-Control", "no-cache")


# Create FastAPI app and attach SocketManager immediately
app = FastAPI(**_fastapi_docs_kwargs())  # Create an instance of FastAPI
fastapi_app = app  # Expose the original FastAPI app for testing
# AI uses each customer's own OpenAI key (app/services/ai/credentials.py);
# OPENAI_API_KEY is only an optional platform fallback for local development.

# Verify PostHog configuration
posthog_api_key = os.getenv("POSTHOG_API_KEY")
if not posthog_api_key:
    logger.warning(
        "POSTHOG_API_KEY is missing in environment variables. Analytics will be disabled."
    )

cors_origins = [
    "https://manifeststartup.com",
    "https://www.manifeststartup.com",
]
if _IS_NON_PROD:
    cors_origins.extend(
        [
            "http://localhost:3000",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
replit_domain = os.getenv("REPLIT_DEV_DOMAIN")
if replit_domain:
    cors_origins.append(f"https://{replit_domain}")
replit_domains = os.getenv("REPLIT_DOMAINS")
if replit_domains:
    # REPLIT_DOMAINS can be a comma-separated list.
    for d in [x.strip() for x in replit_domains.split(",") if x.strip()]:
        cors_origins.append(f"https://{d}")
cors_origins.extend(frontend_origins_from_env())
# De-dup while preserving order (Python 3.7+ dict order).
cors_origins = list(dict.fromkeys(cors_origins))

# Add CORS middleware to the FastAPI application.
# Closes SEC-001 — previously this used wildcard methods/headers/expose,
# which meant a CSRF-bypass header (custom auth or content-type) could be
# sent from any allowed origin. We now enumerate every method/header we
# actually use and only expose the rate-limit headers.
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "X-Requested-With",
    "X-CSRF-Token",
    "x-csrf-token",
    "X-Manifest-Agent-Key",
    "x-manifest-agent-key",
    "X-API-Key",
    "x-api-key",
]
EXPOSED_HEADERS = [
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "Retry-After",
    "X-Step-Up-Required",
    # Stage #1 observability — readable from browser devtools on localhost.
    "X-Request-Id",
    "X-Manifest-Duration-Ms",
    "X-Manifest-GraphQL-Duration-Ms",
    "X-Manifest-DB-Query-Count",
    "X-Manifest-DB-Connection-Count",
]

_cors_kwargs = dict(
    allow_origins=cors_origins,
    allow_credentials=True,  # cookies
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
    expose_headers=EXPOSED_HEADERS,
    max_age=3600,
)
# The localhost-loopback regex stays *only* in non-prod, otherwise a host
# that resolves to 127.0.0.1 via DNS rebinding would re-open SEC-001.
if _IS_NON_PROD:
    _cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(CORSMiddleware, **_cors_kwargs)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# SEC-002: baseline security headers + nonce-based CSP (report-only by
# default — flip to enforced via CSP_ENFORCE=true after the SPA rollout
# has been verified). Registered AFTER CORS so preflight responses also
# get the security headers.
app.add_middleware(SecurityHeadersMiddleware)

app.middleware("http")(track_visitors_middleware)

logger.info("CORS, security-headers, and visitor tracking middleware initialized.")


@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    response = await call_next(request)
    _set_cache_control_headers(request, response)
    return response


# Paths excluded from the per-request DB query metrics. Health/metrics
# endpoints must never appear in slow-request warnings or take a pool
# slot, otherwise a misconfigured scraper can drown the log stream.
_PERF_EXCLUDED_PATHS = frozenset({"/ping", "/metrics", "/health", "/healthz"})


@app.middleware("http")
async def performance_metrics_middleware(request: Request, call_next):
    """Per-request DB query metrics + slow-request log line for ALL routes.

    Previously this only fired for ``/graphql``; Stage #1 of the backend
    migration extends it to REST + the SPA shell so we can see, for
    every endpoint, how many DB round-trips it costs and how long it
    took. Existing ``X-Manifest-GraphQL-Duration-Ms`` header is kept as
    a backward-compatible alias for any consumer that already parses it.
    """
    path = request.url.path
    if path in _PERF_EXCLUDED_PATHS:
        return await call_next(request)

    from app.db.database import begin_query_metrics, end_query_metrics

    is_graphql = path.startswith("/graphql")
    token = begin_query_metrics()
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - started_at) * 1000
        metrics = end_query_metrics(token)
        query_count = int(metrics.get("query_count", 0))
        connection_count = int(metrics.get("connection_count", 0))

        if "response" in locals():
            response.headers["X-Manifest-Duration-Ms"] = f"{duration_ms:.2f}"
            response.headers["X-Manifest-DB-Query-Count"] = str(query_count)
            response.headers["X-Manifest-DB-Connection-Count"] = str(connection_count)
            if is_graphql:
                response.headers["X-Manifest-GraphQL-Duration-Ms"] = f"{duration_ms:.2f}"

        slow_threshold = float(
            os.getenv(
                "SLOW_REQUEST_MS",
                os.getenv("GRAPHQL_SLOW_REQUEST_MS", "750"),
            )
        )
        if duration_ms >= slow_threshold:
            logger.warning(
                (
                    "[performance] slow GraphQL request"
                    if is_graphql
                    else "[performance] slow request"
                ),
                extra={
                    "path": path,
                    "method": request.method,
                    "duration_ms": round(duration_ms, 2),
                    "query_count": query_count,
                    "connection_count": connection_count,
                    "total_query_ms": round(float(metrics.get("total_query_ms", 0.0)), 2),
                    "slow_queries": metrics.get("slow_queries", []),
                },
            )


# Register LAST so RequestIDMiddleware becomes the OUTERMOST middleware.
# Starlette's add_middleware uses `insert(0, ...)`, so the most recent
# registration wraps everything else; the ContextVar is set before any
# other middleware runs and the X-Request-Id response header is appended
# after every other middleware (including error handlers) has finished.
app.add_middleware(AIRequestContextMiddleware)  # per-request OpenAI key (BYOK)
app.add_middleware(RequestIDMiddleware)

# /metrics — Prometheus text exposition for any external scraper.
# Lazy-imports the instrumentator so dev environments without the dep
# still boot. Disable with METRICS_ENABLED=false.
setup_metrics(app)


# --------------------------
# Import Managers
# --------------------------


# --------------------------
# Import and include routes
# --------------------------
import contextlib

from app.routes.account_routes import router as account_router
from app.routes.agent_discovery_routes import router as agent_discovery_router
from app.routes.api_keys_routes import router as api_keys_router
from app.routes.api_v1_routes import router as api_v1_router
from app.routes.auth_routes import router as auth_router
from app.routes.bug_fix_routes import router as bug_fix_router
from app.routes.dsar_admin_routes import router as dsar_admin_router
from app.routes.dsar_routes import router as dsar_router
from app.routes.integration_routes import router as integration_router
from app.routes.oauth_routes import router as oauth_router
from app.routes.oauth_routes import validate_oauth_config
from app.routes.ops_internal_routes import router as ops_internal_router
from app.routes.pitch_reel_routes import router as pitch_reel_router
from app.routes.privacy_routes import router as privacy_router
from app.routes.production_signal_routes import router as production_signal_router
from app.routes.production_test_routes import router as production_test_router
from app.routes.scim_routes import router as scim_router
from app.routes.sso_routes import router as sso_router
from app.routes.step_up_routes import router as step_up_router
from app.routes.survey_ops_routes import router as survey_ops_router
from app.routes.trust_center_routes import router as trust_center_router
from app.routes.voice_agent_routes import router as voice_agent_router
from app.routes.webauthn_routes import router as webauthn_router
from app.routes.website_testing_routes import router as website_testing_router

validate_oauth_config()
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(voice_agent_router)
app.include_router(integration_router)
app.include_router(api_v1_router)
app.include_router(agent_discovery_router)
app.include_router(api_keys_router)
app.include_router(account_router)
app.include_router(privacy_router)
app.include_router(dsar_router)
app.include_router(dsar_admin_router)
app.include_router(trust_center_router)
app.include_router(website_testing_router)
app.include_router(survey_ops_router)
app.include_router(production_signal_router)
app.include_router(production_test_router)
app.include_router(bug_fix_router)
app.include_router(ops_internal_router)
app.include_router(pitch_reel_router)
app.include_router(sso_router)
app.include_router(scim_router)
app.include_router(step_up_router)
app.include_router(webauthn_router)


def get_context(request: Request, response: Response):
    from app.db.database import create_database_client

    if os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from tests import conftest

            db = getattr(conftest, "mock_database_client", None) or create_database_client()
        except Exception:
            db = create_database_client()
    else:
        db = create_database_client()
    return {
        "request": request,
        "response": response,
        "db": db,
    }


graphql_app = GraphQLRouter(schema, context_getter=get_context)

# Add GraphQL endpoint
app.include_router(graphql_app, prefix="/graphql")

# --------------------------
# Root route (moved to after frontend setup for SPA support)
# --------------------------


# --------------------------
# Test route
# --------------------------
@app.get("/ping")
@app.get("/health")
@app.get("/healthz")
async def ping(request: Request):
    if analytics_enabled_for_request(request):
        capture_event(
            request.cookies.get("visitor_id") or "system",
            "ping_request",
            {"path": request.url.path},
        )
    payload: dict[str, object] = {"message": "pong"}

    # Stage #2 — surface async pool readiness on the existing health probe.
    from app.db.async_pool import async_db_enabled, get_async_pool_snapshot, ping_async_db

    if async_db_enabled():
        snapshot = get_async_pool_snapshot()
        payload["async_db"] = {
            "enabled": True,
            "pool_open": snapshot.get("pool_open", False),
            "ping_ok": await ping_async_db() if snapshot.get("pool_open") else False,
        }

    return payload


@app.get("/api/docs")
async def api_docs():
    """Serve API documentation page."""
    docs_path = Path(__file__).resolve().parents[2] / "docs" / "public" / "api" / "index.html"
    if docs_path.exists():
        return FileResponse(docs_path, media_type="text/html")
    return {"message": "API documentation", "endpoints": "/api/v1"}


# --------------------------
# Socket.IO setup and route
# --------------------------
# Closes SEC-004/SEC-005 — Socket.IO previously used `cors_allowed_origins="*"`
# *with* `cors_credentials=True`, which allowed any origin to attach the
# session cookie via a Socket.IO upgrade and bypass the FastAPI CORS allowlist.
# We now reuse the FastAPI allowlist (a list, not "*"), so the engineio CORS
# preflight rejects unknown origins.
sio = socketio.AsyncServer(
    cors_allowed_origins=cors_origins,
    async_mode="asgi",
    logger=True,
    engineio_logger=True,
    socketio_logger=True,
    cors_credentials=True,
)


def _socketio_resolve_user(environ: dict, auth: dict | None) -> str | None:
    """Resolve the authenticated user_id from the engineio environ.

    Closes SEC-005. Accepts either:
      * the session/access_token cookie used by the rest of the app, or
      * an ``auth={"token": "..."}`` payload from `socket.io-client`.

    Returns ``None`` if the caller is unauthenticated; the caller raises
    ``ConnectionRefusedError`` so engineio refuses the handshake.
    """
    import jwt as _jwt
    from app.auth.replit_auth import SESSION_SECRET, get_current_user_from_session
    from app.services.identity.sessions import is_session_active

    class _Req:
        def __init__(self, cookies, headers):
            self.cookies = cookies
            self.headers = headers

    cookies: dict[str, str] = {}
    raw_cookie = environ.get("HTTP_COOKIE")
    if raw_cookie:
        sc = SimpleCookie()
        sc.load(raw_cookie)
        cookies = {k: m.value for k, m in sc.items()}
    headers = {"authorization": environ.get("HTTP_AUTHORIZATION", "")}

    # Cookie path — same helper used by /auth/me and friends.
    payload = get_current_user_from_session(_Req(cookies, headers))
    if payload and payload.get("sub"):
        return str(payload["sub"])

    # auth={"token": "<jwt>"} fallback for native socket-io clients.
    if isinstance(auth, dict):
        tok = auth.get("token") or auth.get("access_token") or auth.get("session_token")
        if tok:
            try:
                p = _jwt.decode(tok, SESSION_SECRET, algorithms=["HS256"])
                sid_claim = p.get("sid")
                user = p.get("sub")
                if user and (not sid_claim or is_session_active(str(sid_claim), str(user))):
                    return str(user)
            except Exception as exc:  # noqa: BLE001
                logger.info("[socketio] auth-token rejected: %s", exc)
    return None


@sio.event
async def connect(sid, environ, auth=None):
    """Authenticated Socket.IO handshake (SEC-005).

    Anonymous clients are refused; legitimate clients have their
    ``user_id`` stashed on the engineio session for per-event authz.
    """
    user_id = _socketio_resolve_user(environ, auth)
    if not user_id:
        logger.warning("[socketio] unauthenticated connect rejected: sid=%s", sid)
        raise ConnectionRefusedError("authentication required")

    logger.info(f"Socket.IO: Client connected: {sid} user={user_id}")
    raw_cookie = environ.get("HTTP_COOKIE")
    analytics_allowed = analytics_enabled_for_cookie_header(raw_cookie)
    await sio.save_session(sid, {"analytics_allowed": analytics_allowed, "user_id": user_id})
    if analytics_allowed:
        cookie = SimpleCookie()
        if raw_cookie:
            cookie.load(raw_cookie)
        distinct_id = cookie.get("visitor_id").value if cookie.get("visitor_id") else user_id
        capture_event(distinct_id, "socket_connected", {"sid": sid, "user_id": user_id})
    await sio.emit("server_message", {"message": "Welcome!"}, to=sid)


async def _socketio_require_user(sid: str) -> str | None:
    """Per-event authz helper — returns the cached user_id or kicks the socket."""
    try:
        session = await sio.get_session(sid)
    except Exception:
        session = {}
    user_id = session.get("user_id")
    if not user_id:
        await sio.disconnect(sid)
        return None
    return user_id


@sio.event
async def disconnect(sid):
    logger.info(f"Socket.IO: Client disconnected: {sid}")
    try:
        session = await sio.get_session(sid)
    except Exception:
        session = {}
    if session.get("analytics_allowed"):
        capture_event(sid, "socket_disconnected", {"sid": sid})


@sio.event
async def client_idea_update(sid, data):
    user_id = await _socketio_require_user(sid)
    if not user_id:
        return
    logger.info(f"Socket.IO: Received idea update from {sid} (user={user_id}): {data}")
    await sio.emit("idea_updated", data)


@sio.event
async def request_similar_ideas(sid, data):
    user_id = await _socketio_require_user(sid)
    if not user_id:
        return
    import asyncio

    idea_id = data.get("idea_id")
    description = data.get("description")
    logger.info(f"Socket.IO: Received request_similar_ideas from {sid}: {data}")

    try:
        loop = asyncio.get_running_loop()  # get the main event loop
        Thread(
            target=generate_background_tasks, args=(description, idea_id, sio, sid, loop)
        ).start()
        logger.info(f"Socket.IO: Background tasks started for idea_id: {idea_id}")
        # Do NOT emit here; emit from inside generate_background_tasks when done
    except Exception as e:
        logger.error(f"Error generating similar ideas: {e}")
        await sio.emit("similar_ideas_result", {"idea_id": idea_id, "error": str(e)}, to=sid)


# Serve frontend static files in production
frontend_build_path = Path(__file__).resolve().parents[2] / "frontend" / "build"
frontend_index_path = frontend_build_path / "index.html"
_frontend_index_template: str | None = None
generated_pdfs_path = Path(__file__).resolve().parents[2] / "generated" / "pdfs"
# API paths that should NOT be caught by the SPA fallback
API_PATHS = ("graphql", "socket.io", "ping", "api")
is_pytest = bool(
    os.getenv("PYTEST_CURRENT_TEST") or "PYTEST_VERSION" in os.environ or "pytest" in sys.modules
)

generated_pdfs_path.mkdir(parents=True, exist_ok=True)
app.mount("/generated/pdfs", StaticFiles(directory=generated_pdfs_path), name="generated-pdfs")


# Run any pending DB migrations at startup (all idempotent)
def _run_startup_migrations() -> None:  # noqa: C901
    try:
        from app.db.database import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Ensure pitch_reels table exists with full schema
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pitch_reels (
                        reel_id UUID PRIMARY KEY,
                        slug VARCHAR(255) NOT NULL UNIQUE,
                        creator_user_id UUID NOT NULL,
                        idea_id UUID,
                        title TEXT NOT NULL,
                        subtitle TEXT,
                        thesis TEXT,
                        description TEXT,
                        creator_role VARCHAR(255),
                        tags JSONB DEFAULT '[]'::jsonb,
                        video_url TEXT,
                        workspace_path TEXT,
                        accent_from VARCHAR(50),
                        accent_to VARCHAR(50),
                        featured_rank INTEGER DEFAULT 0,
                        baseline_like_count INTEGER DEFAULT 0,
                        baseline_comment_count INTEGER DEFAULT 0,
                        baseline_save_count INTEGER DEFAULT 0,
                        baseline_share_count INTEGER DEFAULT 0,
                        is_published BOOLEAN DEFAULT FALSE,
                        video_status VARCHAR(50),
                        video_generation_error TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                """)
                # Add any columns that might be missing from older deployments
                for col_ddl in [
                    "ALTER TABLE pitch_reels ADD COLUMN IF NOT EXISTS idea_id UUID;",
                    "ALTER TABLE pitch_reels ADD COLUMN IF NOT EXISTS video_status VARCHAR(50);",
                    "ALTER TABLE pitch_reels ADD COLUMN IF NOT EXISTS video_generation_error TEXT;",
                    "ALTER TABLE pitch_reels ADD COLUMN IF NOT EXISTS video_data BYTEA;",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_pitch_reels_idea_id_unique ON pitch_reels(idea_id) WHERE idea_id IS NOT NULL;",
                ]:
                    try:
                        cur.execute(col_ddl)
                    except Exception:
                        pass  # Column/index may already exist
                # Ensure survey_responses exists for research + product feedback flows
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS survey_responses (
                        response_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        survey_type TEXT NOT NULL,
                        user_id TEXT,
                        contact_email TEXT,
                        answers JSONB DEFAULT '{}'::jsonb NOT NULL
                    );
                """)
                for col_ddl in [
                    "ALTER TABLE survey_responses ADD COLUMN IF NOT EXISTS user_id TEXT;",
                    "ALTER TABLE survey_responses ADD COLUMN IF NOT EXISTS contact_email TEXT;",
                    "ALTER TABLE survey_responses ADD COLUMN IF NOT EXISTS answers JSONB DEFAULT '{}'::jsonb NOT NULL;",
                    "ALTER TABLE survey_responses ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;",
                    "CREATE INDEX IF NOT EXISTS idx_survey_responses_type_created ON survey_responses(survey_type, created_at DESC);",
                ]:
                    with contextlib.suppress(Exception):
                        cur.execute(col_ddl)
                for users_guest_ddl in [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_guest BOOLEAN NOT NULL DEFAULT FALSE;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS guest_merge_secret TEXT NULL;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS guest_created_at TIMESTAMPTZ NULL;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS guest_expires_at TIMESTAMPTZ NULL;",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ NULL;",
                ]:
                    with contextlib.suppress(Exception):
                        cur.execute(users_guest_ddl)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS privacy_consents (
                        consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        consent_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        user_id TEXT NULL,
                        visitor_id TEXT NULL,
                        source TEXT NOT NULL DEFAULT 'settings',
                        policy_version TEXT NOT NULL,
                        analytics_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        communications_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        do_not_sell_or_share BOOLEAN NOT NULL DEFAULT FALSE,
                        consent_payload JSONB DEFAULT '{}'::jsonb NOT NULL,
                        ip_hash TEXT NULL
                    );
                """)
                for privacy_ddl in [
                    "CREATE INDEX IF NOT EXISTS idx_privacy_consents_user_updated ON privacy_consents(user_id, consent_updated_at DESC) WHERE user_id IS NOT NULL;",
                    "CREATE INDEX IF NOT EXISTS idx_privacy_consents_visitor_updated ON privacy_consents(visitor_id, consent_updated_at DESC) WHERE visitor_id IS NOT NULL;",
                ]:
                    with contextlib.suppress(Exception):
                        cur.execute(privacy_ddl)

                # Password reset tokens: hashed, single-use, short-lived.
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS password_reset_tokens (
                        token_id    BIGSERIAL PRIMARY KEY,
                        user_id     UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        token_hash  VARCHAR(128) NOT NULL UNIQUE,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at  TIMESTAMPTZ NOT NULL,
                        used_at     TIMESTAMPTZ NULL,
                        request_ip  VARCHAR(64) NULL
                    );
                """)
                for prt_ddl in [
                    "CREATE INDEX IF NOT EXISTS idx_prt_user_id ON password_reset_tokens(user_id);",
                    "CREATE INDEX IF NOT EXISTS idx_prt_expires_at ON password_reset_tokens(expires_at);",
                ]:
                    with contextlib.suppress(Exception):
                        cur.execute(prt_ddl)

                # Shared rate-limit counters for the password reset flow.
                # One row per request; the service deletes rows older than
                # the sliding window so the table stays small.
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS password_reset_rate_limit_events (
                        id          BIGSERIAL PRIMARY KEY,
                        bucket_key  VARCHAR(255) NOT NULL,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                for prl_ddl in [
                    "CREATE INDEX IF NOT EXISTS idx_prl_key_created ON password_reset_rate_limit_events(bucket_key, created_at);",
                    "CREATE INDEX IF NOT EXISTS idx_prl_created ON password_reset_rate_limit_events(created_at);",
                ]:
                    with contextlib.suppress(Exception):
                        cur.execute(prl_ddl)

                # Stage #3 — workspace ideas list hot path (see supabase migration
                # 20260523180000_ideas_list_performance.sql).
                for ideas_list_ddl in [
                    "CREATE INDEX IF NOT EXISTS idx_ideas_user_id_created_at ON ideas(user_id, created_at DESC);",
                    "ALTER TABLE ideas ADD COLUMN IF NOT EXISTS generated_asset_count smallint NOT NULL DEFAULT 0;",
                    "ALTER TABLE ideas ADD COLUMN IF NOT EXISTS has_description boolean NOT NULL DEFAULT false;",
                ]:
                    with contextlib.suppress(Exception):
                        cur.execute(ideas_list_ddl)

                # Task #48 — Restore reliable idea deletion in production.
                # Several child tables (comments, intellectual_properties,
                # pitch_decks, product_requirements_documents) historically
                # used the default NO ACTION delete rule on their idea_id
                # foreign key. When a user owns related rows, deleting the
                # parent idea raises foreign_key_violation (SQLSTATE 23503)
                # and the GraphQL resolver returns "Failed to delete idea".
                # Convert each FK to ON DELETE CASCADE so the parent
                # delete atomically removes its children. The DDL is
                # idempotent — each ALTER runs in its own savepoint so a
                # failure on one table (e.g. table not yet created in a
                # fresh deployment) does not abort the rest.
                # Hardcoded baseline of known offenders from the Task #48
                # incident. Tracked as (table, constraint, known_delete_rule)
                # — `None` means "rule unknown, must apply DDL". The dynamic
                # discovery below will overwrite the rule on each entry it
                # finds, so already-CASCADE baseline FKs can skip the
                # lock-heavy DROP/ADD on subsequent restarts. The baseline
                # stays as a belt-and-suspenders safety net in case
                # information_schema discovery fails (e.g. limited DB role
                # on a self-hosted Postgres).
                _idea_cascade_targets: list[tuple[str, str, str | None]] = [
                    ("comments", "comments_idea_id_fkey", None),
                    ("intellectual_properties", "intellectual_properties_idea_id_fkey", None),
                    ("pitch_decks", "pitch_decks_idea_id_fkey", None),
                    (
                        "product_requirements_documents",
                        "product_requirements_documents_idea_id_fkey",
                        None,
                    ),
                ]
                # Schema audit (per code-review follow-up): discover EVERY
                # foreign key that references ideas.idea_id, including any
                # tables we don't know about. For any such FK whose
                # delete_rule is not already CASCADE, recreate it with
                # ON DELETE CASCADE. This guarantees that even tables
                # added by future migrations (or by a downstream fork)
                # cannot break idea deletion with a foreign_key_violation.
                try:
                    cur.execute("""
                        SELECT
                            tc.table_name,
                            tc.constraint_name,
                            rc.delete_rule
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.referential_constraints AS rc
                          ON tc.constraint_name = rc.constraint_name
                         AND tc.table_schema     = rc.constraint_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                          ON ccu.constraint_name = tc.constraint_name
                         AND ccu.constraint_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND ccu.table_name     = 'ideas'
                          AND ccu.column_name    = 'idea_id'
                          AND tc.table_schema    = 'public'
                        """)
                    _discovered_fks = cur.fetchall() or []
                    _baseline_index: dict[tuple[str, str], int] = {
                        (t, c): i for i, (t, c, _) in enumerate(_idea_cascade_targets)
                    }
                    for _row in _discovered_fks:
                        # psycopg2 may return tuples or DictRow; normalize.
                        try:
                            _t, _c, _rule = _row[0], _row[1], _row[2]
                        except Exception:
                            _t = _row.get("table_name")
                            _c = _row.get("constraint_name")
                            _rule = _row.get("delete_rule")
                        if not _t or not _c:
                            continue
                        _key = (_t, _c)
                        if _key in _baseline_index:
                            # Stamp known delete_rule onto the baseline
                            # entry so the DDL loop can skip already-CASCADE
                            # FKs and avoid lock churn on every restart.
                            _idx = _baseline_index[_key]
                            _idea_cascade_targets[_idx] = (_t, _c, _rule)
                        else:
                            _idea_cascade_targets.append((_t, _c, _rule))
                            _baseline_index[_key] = len(_idea_cascade_targets) - 1
                            logger.info(
                                "[Startup] Task #48 schema audit: discovered %s.%s "
                                "(delete_rule=%s)",
                                _t,
                                _c,
                                _rule,
                            )
                except Exception as _audit_exc:
                    logger.warning(
                        "[Startup] Task #48 schema audit could not enumerate "
                        "ideas FKs (proceeding with hardcoded baseline only): %s",
                        _audit_exc,
                    )
                for child_table, constraint_name, current_rule in _idea_cascade_targets:
                    # Skip lock-heavy DROP/ADD when discovery confirmed the
                    # constraint is already CASCADE. `current_rule is None`
                    # means we couldn't read it (e.g. discovery skipped or
                    # failed) — apply DDL defensively in that case.
                    if current_rule and current_rule.upper() == "CASCADE":
                        logger.info(
                            "[Startup] Task #48: %s.%s already CASCADE — skipping DDL",
                            child_table,
                            constraint_name,
                        )
                        continue
                    try:
                        cur.execute("SAVEPOINT cascade_fix")
                        cur.execute(
                            f'ALTER TABLE "{child_table}" '
                            f'DROP CONSTRAINT IF EXISTS "{constraint_name}";'
                        )
                        cur.execute(
                            f'ALTER TABLE "{child_table}" '
                            f'ADD CONSTRAINT "{constraint_name}" '
                            f'FOREIGN KEY ("idea_id") '
                            f'REFERENCES "ideas"("idea_id") '
                            f"ON DELETE CASCADE;"
                        )
                        cur.execute("RELEASE SAVEPOINT cascade_fix")
                        logger.info(
                            "[Startup] Task #48: ON DELETE CASCADE applied to %s.%s",
                            child_table,
                            constraint_name,
                        )
                    except Exception as _cascade_exc:
                        try:
                            cur.execute("ROLLBACK TO SAVEPOINT cascade_fix")
                            cur.execute("RELEASE SAVEPOINT cascade_fix")
                        except Exception:
                            pass
                        logger.warning(
                            "[Startup] Task #48: could not enforce CASCADE on " "%s (%s): %s",
                            child_table,
                            constraint_name,
                            _cascade_exc,
                        )
        logger.info(
            "[Startup] DB migrations applied to pitch_reels, survey_responses, users guest columns, password_reset_tokens, password_reset_rate_limit_events, and idea-child FK cascade fix (Task #48)."
        )
    except Exception as _mig_exc:
        logger.warning("[Startup] Could not run DB migration: %s", _mig_exc)

    # Task #14 — Audit chain schema (idempotent). Runs before data-protection
    # so the very first event recorded after boot is already on the chain.
    try:
        from scripts.setup_audit_chain_tables import (
            setup_audit_chain_tables as _run_audit_chain_migration,
        )

        _run_audit_chain_migration()
        logger.info("[Startup] Task #14 audit-chain schema applied.")
    except Exception as _ac_exc:
        logger.warning("[Startup] Task #14 audit-chain migration failed: %s", _ac_exc)

    # Task #12 — Data protection schema (idempotent).
    try:
        from scripts.setup_data_protection_tables import (
            setup_data_protection_tables as _run_data_protection_migration,
        )

        _run_data_protection_migration()
        logger.info("[Startup] Task #12 data-protection schema applied.")
    except Exception as _dp_exc:
        logger.warning("[Startup] Task #12 data-protection migration failed: %s", _dp_exc)

    # Task #15 — DSAR operations workflow + breach-timer schema.
    try:
        from scripts.setup_dsar_workflow_tables import (
            setup_dsar_workflow_tables as _run_dsar_workflow_migration,
        )

        _run_dsar_workflow_migration()
        logger.info("[Startup] Task #15 DSAR workflow schema applied.")
    except Exception as _dwf_exc:
        logger.warning("[Startup] Task #15 DSAR workflow migration failed: %s", _dwf_exc)

    # Task #12 — Production KEK policy: refuse to boot in production if the
    # active KEK would resolve to the dev fallback (provider returned no
    # key). Catches accidental misconfiguration of MANIFEST_ENV vs the
    # configured KEK provider/material.
    _env_label = (os.getenv("MANIFEST_ENV") or os.getenv("ENVIRONMENT") or "").lower()
    if _env_label == "production":
        try:
            from app.security.crypto import get_active_kek_version
            from app.security.kek_provider import get_provider

            _active = get_active_kek_version()
            _key = get_provider().load(_active)
            if _key is None:
                raise RuntimeError(
                    f"Production boot refused: KEK v{_active} not available from "
                    f"provider {os.getenv('MANIFEST_KEK_PROVIDER', 'env')!r}."
                )
            logger.info(
                "[Startup] Production KEK policy OK (provider=%s, active_version=%s).",
                os.getenv("MANIFEST_KEK_PROVIDER", "env"),
                _active,
            )
        except Exception as _kek_exc:
            logger.error("[Startup] Production KEK policy violation: %s", _kek_exc)
            raise


if not is_pytest:
    _run_startup_migrations()


# ---------------------------------------------------------------------------
# Periodic sweep of stale password-reset rate-limit rows.
#
# The shared rate limiter (Postgres-backed) only deletes rows lazily —
# when the same bucket key is hit again. Buckets that fire once and
# never repeat would otherwise leave rows behind forever, slowly
# bloating the table and degrading the sliding-window query. A daemon
# thread runs `sweep_stale_rate_limit_rows()` once an hour to keep the
# table bounded without operators needing to run a manual DELETE.
# ---------------------------------------------------------------------------
def _start_password_reset_rate_limit_sweeper() -> None:
    from threading import Event, Thread

    from app.services.identity.password_reset import sweep_stale_rate_limit_rows

    raw = os.getenv("PASSWORD_RESET_SWEEP_INTERVAL_SEC", "3600")
    try:
        interval_sec = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "[Startup] Invalid PASSWORD_RESET_SWEEP_INTERVAL_SEC=%r; falling back to 3600s.",
            raw,
        )
        interval_sec = 3600
    if interval_sec <= 0:
        logger.info(
            "[Startup] Password-reset rate-limit sweeper disabled "
            "(PASSWORD_RESET_SWEEP_INTERVAL_SEC=%s).",
            interval_sec,
        )
        return

    stop_event = Event()

    def _loop() -> None:
        # Run one sweep promptly after boot (with a small delay so it
        # doesn't race startup migrations / first connections), then
        # settle into the hourly cadence. Without this, stale rows
        # left over from the previous process lifetime would persist
        # for a full interval before the first cleanup.
        if stop_event.wait(30):
            return
        try:
            sweep_stale_rate_limit_rows()
        except Exception as exc:
            logger.warning("[password_reset] Initial sweep failed: %s", exc)
        while not stop_event.wait(interval_sec):
            try:
                sweep_stale_rate_limit_rows()
            except Exception as exc:  # defensive: never let the loop die
                logger.warning("[password_reset] Sweeper iteration failed: %s", exc)

    Thread(
        target=_loop,
        name="password-reset-rate-limit-sweeper",
        daemon=True,
    ).start()
    logger.info(
        "[Startup] Password-reset rate-limit sweeper running every %ds.",
        interval_sec,
    )


if not is_pytest:
    _start_password_reset_rate_limit_sweeper()

if frontend_build_path.exists() and frontend_index_path.exists() and not is_pytest:
    logger.info(f"Serving frontend static files from: {frontend_build_path}")

    # Mount static assets (CRA uses /static, Vite uses /assets)
    static_path = frontend_build_path / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")
    assets_path = frontend_build_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    def _frontend_index_html() -> str:
        global _frontend_index_template
        if _frontend_index_template is None:
            _frontend_index_template = frontend_index_path.read_text(encoding="utf-8")
        return _frontend_index_template

    register_spa_fallback(app, frontend_build_path, _frontend_index_html)

else:
    logger.info("Frontend build not found or incomplete. Static file serving disabled.")

    @app.get("/")
    async def root(request: Request):
        if analytics_enabled_for_request(request):
            capture_event(
                request.cookies.get("visitor_id") or "system",
                "api_accessed",
                {"endpoint": "/"},
            )
        return {"message": "Manifest API is live"}


@app.on_event("startup")
async def _startup_async_db_pool() -> None:
    from app.db.async_pool import init_async_pool

    await init_async_pool()


@app.on_event("shutdown")
async def _shutdown_async_db_pool() -> None:
    from app.db.async_pool import close_async_pool

    await close_async_pool()


app = ASGIApp(sio, other_asgi_app=app)

# Outermost layer: reject traffic that bypassed the Cloudflare edge Worker
# (no-op unless EDGE_SHARED_SECRET is set). See app/security/edge_guard.py.
from app.security.edge_guard import EdgeGuardMiddleware  # noqa: E402

app = EdgeGuardMiddleware(app)
