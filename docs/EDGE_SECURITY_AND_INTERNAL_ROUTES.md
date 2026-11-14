# Edge security, WAF, and internal route exposure

Last updated **May 3, 2026**.

This document captures **operational** guidance for CDN/WAF placement and an inventory-style review of **internal** HTTP surfaces in Manifest.

## Edge: WAF and rate limiting

**Goals**

- Mitigate credential stuffing, scraping, and volumetric abuse before traffic hits the origin.
- Reduce load on Postgres-backed rate limiting ([`RateLimitService`](backend/app/services/rate_limit_service.py)) under attack.

**Practices**

1. Put the **public web app and API** behind a CDN or reverse proxy that supports WAF rules (OWASP CRS baseline, geo blocks if appropriate, bot management if budget allows).
2. Apply **strict rate limits** at the edge for anonymous paths (`/graphql` unauthenticated traffic, `/auth/*`, marketing pages) with higher caps for authenticated or API-key traffic where identifiable.
3. Keep **origin-only** routes (if any) off public DNS; use private networking or separate listener ports restricted by firewall.

**Headers**

- Manifest already applies security headers via `SecurityHeadersMiddleware` (`backend/app/security/security_headers.py`). WAF should not strip security headers on responses.

## Internal and high-privilege route prefixes

These routes are **not** for end users; protect with secrets, network policy, or both.

| Prefix | Purpose | Auth pattern |
|--------|---------|----------------|
| `/api/internal/production-signals/*` | Production anomaly ingest | `X-Manifest-Agent-Key` + `MANIFEST_AGENT_LOOP_SECRET` / `AGENT_LOOP_SECRET` |
| `/api/internal/website-testing/*` | Website audit / GitHub sync | Same agent key |
| `/api/internal/survey-ops/*` | Survey analytics automation | Same agent key |
| `/api/internal/ops/*` | Ops snapshot for metrics | Same agent key ([docs/API.md](API.md)) |

All of the above use `require_agent_loop_key` in `backend/app/routes/dependencies.py`.

**Review checklist (quarterly or on release)**

1. Confirm `include_in_schema=False` remains set on internal routers so they do not appear in public OpenAPI when docs are enabled in dev.
2. Confirm production keeps FastAPI’s built-in OpenAPI disabled unless `ENABLE_INTERNAL_API_DOCS` is explicitly enabled (`backend/app/main.py`).
3. Grep for new `APIRouter(prefix="/api/internal` registrations in `backend/app/main.py` and route modules; update this table.
4. Verify `MANIFEST_AGENT_LOOP_SECRET` is **long, random, and rotated** on the same schedule as other production secrets.

## GraphQL and REST public surfaces

- Primary app API: `POST /graphql` — rely on resolver-level auth and `_require_full_account` patterns ([`backend/app/graphql/schema.py`](backend/app/graphql/schema.py)).
- Public REST: `/api/v1/*` — API key auth; monitor for key leakage and unusual geographic usage in logs.

## Related documentation

- [docs/OBSERVABILITY_AND_SLO.md](OBSERVABILITY_AND_SLO.md) — monitoring internal health.
- [docs/API.md](API.md) — full route list and auth notes.
