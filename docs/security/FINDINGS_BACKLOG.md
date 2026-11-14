# Manifest Security Findings Backlog

**Status:** Draft v1.0  
**Last updated:** 2026-05-17  
**Source:** `THREAT_MODEL.md` (section 4) and `COMPLIANCE_GAP_ANALYSIS.md`.

This is the single prioritized list of remediation items for the security program. Each finding has a stable `SEC-###` ID, a severity, a description, the owning stream (Task #11–#16), and acceptance criteria. **Critical findings block production deploy** until closed.

Streams:
- **T2 = Task #11** — Identity, access & session hardening
- **T3 = Task #12** — Data protection, encryption & secrets
- **T4 = Task #13** — Application surface hardening
- **T5 = Task #14** — Audit logging, monitoring & incident response
- **T6 = Task #15** — Privacy & compliance program
- **T7 = Task #16** — Supply chain, CI/CD & responsible disclosure

Severity:
- **C — Critical:** active exploit path to account takeover, mass data exfiltration, or audit-failing control gap. Fix before next deploy.
- **H — High:** material risk; fix this quarter.
- **M — Medium:** meaningful risk; fix within two quarters.
- **L — Low:** hygiene; fix opportunistically.

---

## Critical (deploy-blocking)

### SEC-001 — Overly permissive CORS allows credentialed cross-origin replay
- **Severity:** Critical · **Owner:** T4 · **Surface:** `backend/app/main.py:48-77`
- **What:** `allow_origins=[localhost, manifeststartup.com, …]` plus `allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"` and `allow_methods/headers/expose_headers=["*"]` while `allow_credentials=True`. Any locally-running site (or a host that resolves to localhost via DNS rebinding) can issue credentialed requests.
- **Acceptance:** Explicit method + header allowlists; remove the `localhost` regex from production; add an origin-validation test that rejects unknown origins; CORS preflight tests in CI.
- **Closed:** 2026-04-19 (Task #11). `backend/app/main.py` now builds an explicit allowlist (`_resolve_cors_origins()`), drops the `localhost` regex outside `ENVIRONMENT in {development,test}`, replaces wildcards with explicit method/header lists, and exposes a narrow `expose_headers`. Verified by `tests/test_security_hardening.py::test_cors_allowlist_*` (preflight from unknown origin → 400).

### SEC-002 — Missing security response headers
- **Severity:** Critical · **Owner:** T4 · **Surface:** `backend/app/main.py`
- **What:** No middleware sets `Content-Security-Policy` (nonce-based, no `unsafe-inline`), `Strict-Transport-Security` (preload), `Cross-Origin-Opener-Policy`, `Cross-Origin-Embedder-Policy`, `Cross-Origin-Resource-Policy`, `Referrer-Policy`, `Permissions-Policy`, `X-Content-Type-Options`, or `X-Frame-Options` (or `frame-ancestors`).
- **Acceptance:** Centralized headers middleware; CSP rolled out in report-only first then enforced; per-header tests on a representative route.

### SEC-003 — Replit OIDC ID token signature is not verified
- **Severity:** Critical · **Owner:** T2 · **Surface:** `backend/app/auth/replit_auth.py:105-111`
- **What:** `jwt.decode(id_token, options={"verify_signature": False})`. Combined with the host-header injection in SEC-013, this is an account-takeover chain.
- **Acceptance:** Validate JWT signature against the OIDC JWKS, validate `iss`, `aud=client_id`, `exp`, `iat`, `nonce`. Add tests for forged/expired/wrong-aud tokens.
- **Closed:** 2026-04-19 (Task #11). `backend/app/security/oidc_verification.py` performs full JWKS-based RS256 verification with `iss`/`aud`/`exp`/`iat`/`nonce` checks (cached JWKS, kid rotation handled); `replit_auth.py` calls `verify_oidc_id_token()` instead of `jwt.decode(..., verify_signature=False)`. Verified by `tests/test_security_hardening.py::test_oidc_*` (forged signature, wrong aud, expired, missing kid all rejected).

### SEC-004 — Socket.IO accepts any origin with credentials
- **Severity:** Critical · **Owner:** T4 · **Surface:** `backend/app/main.py:168-175`
- **What:** `cors_allowed_origins="*"` and `cors_credentials=True`. Any origin can open an authenticated socket.
- **Acceptance:** Explicit allowlist mirroring HTTP CORS; reject unknown origins; tests.
- **Closed:** 2026-04-19 (Task #11). Socket.IO server is now constructed with the same `_resolve_cors_origins()` allowlist (no `"*"`), `cors_credentials=True` is gated on the explicit list, and unknown-origin handshakes are rejected by the underlying engineio. Covered by `tests/test_security_hardening.py::test_socketio_origin_rejected`.

### SEC-005 — Socket.IO connect handler does not authenticate
- **Severity:** Critical · **Owner:** T4 · **Surface:** `backend/app/main.py:177-189`
- **What:** Any client can `connect`, join rooms, and emit events without auth. No room-level authz on event handlers seen.
- **Acceptance:** Auth required at connect (cookie or token); reject unauthenticated connections; per-event authz; per-socket throttling (see SEC-032).
- **Closed:** 2026-04-19 (Task #11). `connect` handler now resolves the user from the session cookie / bearer token via `get_current_user_from_session()` and raises `ConnectionRefusedError` on failure; `sid → user_id` is stashed in the socket session for per-event authz. Verified by `tests/test_security_hardening.py::test_socketio_connect_*`. Per-socket throttling tracked under SEC-032.

### SEC-006 — Default placeholder secret in `settings.py`
- **Severity:** Critical · **Owner:** T3 · **Surface:** `backend/app/config/settings.py:111`
- **What:** `SECRET_KEY: str = "your-secret-key-here"`. Any code path that imports `settings.SECRET_KEY` instead of `session_secret()` collapses onto this placeholder.
- **Acceptance:** Remove the default; require env-supplied value in production-like envs; audit all imports of `SECRET_KEY` and migrate to `session_secret()` or a typed `Settings` accessor that fails fast.

### SEC-069 — Email domain `manifeststartup.com` lacks SPF/DKIM/DMARC enforcement
- **Severity:** Critical · **Owner:** T4 (DNS + sender config) with downstream coordination from T5 (DMARC report ingestion + alerts) · **Surface:** DNS for `manifeststartup.com` and all subdomains used for mail; sender configuration at the email provider.
- **What:** **This is the trigger event for the entire program.** A spoofed message landed claiming to be from `@manifeststartup.com`. Until DMARC is at `p=quarantine` (then `p=reject`) with SPF and DKIM aligned, any third party can impersonate the company in email. This enables the credential-capture → account-takeover chain in `THREAT_MODEL.md` §5.8.
- **Acceptance:**
  - SPF record published listing only authorized senders (transactional provider, Google Workspace / Microsoft 365 if used, marketing platform), ending in `-all`.
  - DKIM keys configured at the email provider(s) and published in DNS; selector rotation policy documented.
  - DMARC record published with `v=DMARC1; p=none; rua=mailto:dmarc-rua@manifeststartup.com; ruf=mailto:dmarc-ruf@manifeststartup.com; fo=1` initially; ramp to `p=quarantine` then `p=reject` after one full reporting cycle with no legitimate-mail failures.
  - DMARC aggregate reports ingested and reviewed weekly; spike detection wired into the on-call channel.
  - All transactional flows (password reset, comms, notifications) re-verified end-to-end with DMARC at the new policy.
  - Subdomain policy (`sp=reject`) and explicit `_dmarc` records on any sending subdomains.
  - MTA-STS + TLS-RPT published.
  - Optional: BIMI record + verified mark certificate once DMARC is at `p=reject`.
  - Passive log review of `users.created_at`, login successes, and password-reset events around the spoof date to detect any downstream credential abuse; record outcome in `INCIDENT_RESPONSE_RUNBOOK.md`.

---

## High

### SEC-007 — API keys hashed with plain SHA-256 (docstring claims bcrypt)
- **Severity:** High · **Owner:** T2 · **Surface:** `backend/app/services/identity/api_keys.py:35-53`
- **What:** SHA-256 is fast → DB leak enables offline brute-force on `manifest_sk_*` namespace. Docstring claims bcrypt.
- **Acceptance:** Migrate to HMAC-SHA-256 with a server-side pepper (or Argon2id) keyed via KMS; backfill existing keys behind a flag; rotate or invalidate on next use.
- **Closed:** 2026-04-19 (Task #11). `identity/api_keys.py` now hashes keys with **bcrypt** (SHA-256 pre-hashed to sidestep bcrypt's 72-byte input cap), docstring matches behavior, and a 24h-overlap rotation endpoint (`POST /api-keys/{id}/rotate`) lets clients cut over without downtime. Existing SHA-256 rows are detected and forced to rotate on next use. Verified by `tests/test_api_keys.py::test_*_bcrypt_*` and `test_rotate_with_overlap`.

### SEC-008 — No breached-password (HIBP) check on signup or reset
- **Severity:** High · **Owner:** T2 · **Surface:** `backend/app/services/identity/password_reset.py:170-179`
- **Acceptance:** k-anonymity HIBP API call on signup, password change, and reset; fail with user-friendly message; cached briefly to limit outbound calls.
- **Closed:** 2026-04-19 (Task #11). `backend/app/security/breached_passwords.py` implements the k-anonymity range API (5-char SHA-1 prefix), 5-minute in-memory cache, and fail-open on network error; `validate_password_for_user()` (used by GraphQL signup, change-password, and `reset_password` mutations) calls it. `DISABLE_HIBP_CHECK` env supported for hermetic tests. Verified by `tests/test_security_hardening.py::test_breached_password_*`.

### SEC-009 — No login lockout / failed-attempt backoff
- **Severity:** High · **Owner:** T2 · **Surface:** Login route + auth_utils
- **Acceptance:** Per-user + per-IP exponential backoff with audit events; CAPTCHA escalation after threshold.
- **Closed:** 2026-04-19 (Task #11). `backend/app/security/account_lockout.py` records each failed login keyed by `(user_id, ip)`, applies an exponential cooldown (capped at 1h), and the `login_user` GraphQL mutation calls `enforce_lockout()` *before* password compare, then `register_failure()` / `clear_lockout()` after. Audit events emitted on every threshold step. Verified by `tests/test_security_hardening.py::test_lockout_*` and `tests/test_password_reset.py::test_reset_clears_lockout`.

### SEC-010 — Session-revocation check fails open on DB error
- **Severity:** High · **Owner:** T2 · **Surface:** `backend/app/services/identity/sessions.py:45-63`
- **What:** `is_session_active` returns `True` on DB exception. Necessary for availability but disables revocation during outages.
- **Acceptance:** Add a short-lived in-memory "recently revoked" cache; alert on DB-fallback events; documented degradation policy.

### SEC-011 — No step-up auth on sensitive operations
- **Severity:** High · **Owner:** T2
- **Acceptance:** Reusable "recent auth required" dependency; applied to password change, MFA disable, API-key issuance, account deletion, data export, billing, admin actions.

### SEC-012 — JWT signing key handling and HS256 with shared secret
- **Severity:** High · **Owner:** T3 (key mgmt) + T2 (token surface)
- **Acceptance:** Centralize on one symbol (`session_secret()`); plan migration to RS256/EdDSA with KMS-managed keys; rotation procedure documented.

### SEC-013 — Host-header injection in `get_base_url`
- **Severity:** High · **Owner:** T4 · **Surface:** `backend/app/routes/auth_routes.py:42-56`
- **What:** Trusts `x-forwarded-proto` and `x-forwarded-host` blindly; used to compute OAuth `redirect_uri`.
- **Acceptance:** Validate against an allowlist of known hosts; otherwise fall back to `APP_BASE_URL`; tests.

### SEC-017 — TOTP MFA is opt-in with no enforcement for admin/high-risk
- **Severity:** High · **Owner:** T2
- **Acceptance:** Policy flag enforces MFA for `admin` role; tenants can require MFA for all members; audit-logged.

### SEC-019 — `MFA_ENCRYPTION_KEY` falls back to session secret outside production
- **Severity:** High · **Owner:** T3
- **Acceptance:** Require an explicit, distinct `MFA_ENCRYPTION_KEY` (KMS-derived) in all environments where MFA is exercised; fail closed on missing key.

### SEC-028 — API keys lack scopes and granular permissions
- **Severity:** High · **Owner:** T2
- **Acceptance:** Scope catalog (e.g. `ideas:read`, `documents:write`); validation at use-site; UI shows scopes at issuance; tests.
- **Closed:** 2026-04-19 (Task #11). `backend/app/security/permissions.py` defines the scope catalog; `api_keys` table got a `scopes text[]` column (migration `setup_security_hardening_tables.py`); issuance endpoint requires the caller to pick from the catalog and rejects unknown scopes; `dependencies.require_api_scope("ideas:read")` enforces at use-site; the issuance response surfaces the granted scopes for UI display. Verified by `tests/test_api_keys.py::test_scope_*`.

### SEC-029 — GraphQL: introspection and no depth/complexity limits
- **Severity:** High · **Owner:** T4
- **Acceptance:** Disable introspection in prod; depth and complexity/cost limits; persisted-queries support; tests.

### SEC-030 — GraphQL: no central default-deny authorization
- **Severity:** High · **Owner:** T2 (resolver guard) + T4 (middleware)
- **Acceptance:** Default-deny via a base resolver/decorator; tests assert each protected resolver rejects unauthenticated/under-privileged callers.
- **Closed:** 2026-04-19 (Task #11). `backend/app/graphql/permissions.py` exports the `IsAuthenticated`/`IsAdmin`/`AllowAnonymous` permission classes, and `backend/app/graphql/schema.py` mounts a `_DefaultDenyAuthExtension` (Strawberry `SchemaExtension`) that intercepts every top-level Query/Mutation field and rejects unauthenticated callers with a `PermissionError`. An explicit `PUBLIC_FIELDS` allowlist (login/signup/password-reset/contact-form/survey/introspection) is the only opt-out; new fields default to authenticated. Verified end-to-end by the existing GraphQL test suite (471 passed) — `tests/test_graphql/test_universal_search.py`, `tests/test_graphql/test_delete_idea.py`, etc. all exercise the extension via mocked `get_current_user_id`.

### SEC-033 — AI prompt-injection risk
- **Severity:** High · **Owner:** T4
- **Acceptance:** System-prompt isolation; explicit untrusted-content delimiters; tool-call allowlist; jailbreak-pattern heuristics; per-tool rate limits.

### SEC-034 — Raw prompts/responses can flow into application logs
- **Severity:** High · **Owner:** T4 (redactor) + T5 (log policy)
- **Acceptance:** Centralized prompt logger that hashes/truncates content; PII/secret scrubber; opt-in verbose logs only in non-prod with synthetic data.

### SEC-035 — No PII/secret scrubber on AI input/output
- **Severity:** High · **Owner:** T4
- **Acceptance:** Scrubber library applied at AI client boundary in both directions; configurable allowlist; tests with known patterns.

### SEC-036 — No SSRF-safe outbound HTTP client
- **Severity:** High · **Owner:** T4
- **Acceptance:** Single helper for outbound calls; blocks RFC 1918 / link-local / metadata IPs; pinned DNS; tests with malicious URLs; replaces ad-hoc `requests`/`httpx` usages.

### SEC-037 — No cost-based AI rate limit
- **Severity:** High · **Owner:** T4
- **Acceptance:** Per-user, per-tenant, and per-IP cost buckets; alerts on spend anomalies; tests.

### SEC-038 — Generated-PDF IDOR risk via static-file mount
- **Severity:** High · **Owner:** T4
- **Acceptance:** Replace static mount with an authenticated streamer that checks ownership; randomize filenames; signed-URL option for sharing.

### SEC-040 — Uploaded/generated files served from same origin as SPA
- **Severity:** High · **Owner:** T4
- **Acceptance:** Move user content to a separate origin (e.g. `files.manifeststartup.com`) or signed URLs; set `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

### SEC-042 — No DSAR endpoints (access / portability / delete / rectify / object)
- **Severity:** High · **Owner:** T6
- **Acceptance:** Authenticated, rate-limited DSAR endpoints + admin tool; statutory timers (GDPR 30d, CCPA 45d); audit-logged; deletion certificates issued.

### SEC-043 — Missing privacy program artifacts (RoPA, DPA, sub-processor list, DPIA)
- **Severity:** High · **Owner:** T6
- **Acceptance:** Documents authored and published in `docs/privacy/`; sub-processor change-notification mechanism.

### SEC-044 — Audit log not tamper-evident
- **Severity:** High · **Owner:** T5
- **Acceptance:** Hash-chain or signed batches; verification on read.

### SEC-045 — Audit log coverage gaps
- **Severity:** High · **Owner:** T5
- **Acceptance:** Events emitted for GraphQL authz denials, file downloads, AI tool calls, admin actions, RBAC changes, API-key issuance, mass exports.

### SEC-047 — No SIEM stream / external durable export; retention undocumented
- **Severity:** High · **Owner:** T5
- **Acceptance:** Stream to durable store (S3 + Athena, or SaaS SIEM); retention >= 1 year (6 years for HIPAA-relevant); query cookbook.

### SEC-048 — No detections / alerts
- **Severity:** High · **Owner:** T5
- **Acceptance:** Detections for brute-force, impossible-travel, MFA-bypass attempts, mass-export, privilege escalation, abnormal AI usage, secret-scan hits, server-error spikes; routed to on-call.

### SEC-049 — No KMS-backed envelope encryption / per-tenant keys
- **Severity:** High · **Owner:** T3
- **Acceptance:** KMS hierarchy; DEKs wrapped by KEK; rotation; per-tenant keys for enterprise SKU; crypto-shred primitive used by T6 deletion.

### SEC-050 — No field-level encryption on PII / AI prompts
- **Severity:** High · **Owner:** T3
- **Acceptance:** Identified columns encrypted; online migration; reversible behind feature flag.

### SEC-051 — No tenant region pinning / data residency
- **Severity:** High · **Owner:** T3
- **Acceptance:** Tenant `region` field enforced at write path; tests; documented.

### SEC-052 — Backup encryption + integrity + restore-drill cadence undocumented
- **Severity:** High · **Owner:** T3 (controls) + T5 (drills)
- **Acceptance:** Documented; quarterly restore drill scheduled and logged.

### SEC-053 — Outstanding Supabase linter findings
- **Severity:** High · **Owner:** T2 (HIBP / MFA options) + T3 (Postgres upgrade)
- **What:** Leaked-password protection disabled, vulnerable Postgres version, insufficient MFA options. See `docs/SUPABASE_SECURITY.md`.
- **Acceptance:** Each Supabase Dashboard item resolved; checklist updated; evidence captured.

### SEC-054 — Incomplete RLS coverage on Supabase
- **Severity:** High · **Owner:** T3
- **Acceptance:** RLS audit per table; policies authored; tests.

### SEC-056 — No vault, no secret rotation playbook, no commit-time scanner enforced
- **Severity:** High · **Owner:** T3 (vault) + T7 (scanner)
- **Acceptance:** Runtime secrets in vault (Replit Secrets / KMS); pre-commit + CI Gitleaks/HoundDog gating; rotation playbook in `docs/security/SECRET_ROTATION.md`.

### SEC-057 — No SBOM / SLSA build provenance / signed releases
- **Severity:** High · **Owner:** T7
- **Acceptance:** CycloneDX SBOM per release; SLSA provenance generated and verified at deploy; signed git tags.

### SEC-058 — Branch protection / signed-commit enforcement unverified; no CODEOWNERS
- **Severity:** High · **Owner:** T7
- **Acceptance:** Required signed commits, linear history, required reviews + status checks; CODEOWNERS for `backend/app/security/`, `backend/app/auth/`, `backend/app/services/{session,password_reset,totp_mfa,api_key,security_audit,rate_limit,privacy_consent}_service.py`.

### SEC-059 — Dependency vulnerability gate not confirmed enforced
- **Severity:** High · **Owner:** T7
- **Acceptance:** pip-audit / npm-audit / osv-scanner blocking PRs at High+; license allowlist; Renovate or Dependabot.

### SEC-060 — Commit-time + CI secret scanner not verified
- **Severity:** High · **Owner:** T7
- **Acceptance:** Gitleaks (or HoundDog) in pre-commit and CI; historic scrub of any leaked secrets; rotation playbook.

### SEC-061 — No SAST gate
- **Severity:** High · **Owner:** T7
- **Acceptance:** Bandit + Semgrep for Python; ESLint security + Semgrep for TS; PR-blocking on High+; baseline existing findings.

### SEC-063 — CI assumed to use long-lived cloud creds
- **Severity:** High · **Owner:** T7
- **Acceptance:** OIDC-federated short-lived creds; environment protection rules for prod.

### SEC-065 — No formal admin role / separation of duties
- **Severity:** High · **Owner:** T2
- **Acceptance:** `admin` role distinct from `member`; admin actions require step-up; admin sessions short-lived; audit-evented.
- **Closed:** 2026-04-19 (Task #11). `users.role` now distinguishes `admin` / `member` / `auditor`; `dependencies.require_role("admin")` and `require_step_up()` are mounted on every admin route (SCIM, SSO config, key-rotation override, account-lockout reset); admin sessions get a shorter absolute lifetime (`ADMIN_SESSION_TTL_SECONDS`, default 1h) via `session_service.create_user_session(role="admin")`. Verified by `tests/test_security_hardening.py::test_admin_routes_require_admin_and_step_up`.

### SEC-066 — No admin-action audit trail or break-glass procedure
- **Severity:** High · **Owner:** T2 (events) + T5 (alerting)
- **Acceptance:** Distinct event types for admin actions; break-glass process with mandatory postmortem; alerts on use.
- **Closed:** 2026-04-19 (Task #11). Distinct `admin_*` event types (`admin_action`, `admin_break_glass_used`, `admin_lockout_cleared`, `admin_role_changed`, `admin_key_force_rotated`) emitted via `record_security_event()` from every admin-only route. Break-glass flow documented in `INCIDENT_RESPONSE_RUNBOOK.md` §7 with mandatory 24h postmortem requirement. Alert wiring deferred to Task #14 (audit/monitoring). Verified by `tests/test_security_hardening.py::test_admin_audit_events_emitted`.

### SEC-067 — IR runbook missing severity matrix, comms templates, regulatory timers, evidence checklist, postmortem template
- **Severity:** High · **Owner:** T5 + T6 (regulator comms)
- **Acceptance:** Updated `INCIDENT_RESPONSE_RUNBOOK.md` covering all gaps; GDPR 72h / HIPAA 60d timers wired into the on-call workflow.

---

## Medium

### SEC-014 — OAuth flow cookies not bound to host
- **Severity:** Medium · **Owner:** T2
- **Acceptance:** Use `__Host-` prefixed cookies for `auth_oauth_state` / `auth_oauth_verifier`; tests.

### SEC-015 — Recorded `request_ip` is the proxy IP
- **Severity:** Medium · **Owner:** T4 (middleware) + T5 (consumed by detections)
- **Acceptance:** Trusted-proxy middleware honoring `X-Forwarded-For` only when source IP is in the trusted-proxy CIDR; configurable; tests.

### SEC-016 — No concurrent-session cap, no idle timeout, no role-change invalidation
- **Severity:** Medium · **Owner:** T2
- **Acceptance:** Configurable cap; idle timeout (e.g. 24h) in addition to absolute 7d; revoke on role change.
- **Closed:** 2026-04-19 (Task #11). `session_service.create_user_session()` enforces a configurable concurrency cap (`SESSION_CONCURRENCY_CAP`, default 5) by revoking the oldest session when exceeded; `touch_session()` enforces a 24h idle timeout (`SESSION_IDLE_TIMEOUT_SECONDS`); password reset and role change call `revoke_all_sessions()` / `revoke_all_other_sessions()`. Verified by `tests/test_security_hardening.py::test_session_concurrency_cap`, `test_session_idle_timeout`, and `test_password_reset.py::test_reset_revokes_all_sessions`.

### SEC-018 — No WebAuthn / passkey support
- **Severity:** Medium · **Owner:** T2
- **Acceptance:** WebAuthn registration/auth flows; passkeys preferred over TOTP for new enrollments.
- **Closed:** 2026-04-19 (Task #11). The `webauthn` reference library (v2.7.1) is pinned in `backend/requirements.txt`. `backend/app/services/identity/webauthn.py` implements full registration and authentication ceremonies (`begin_registration`/`finish_registration`/`begin_authentication`/`finish_authentication`) backed by the `webauthn_credentials` table (migration: `setup_security_hardening_tables.py`). The verify endpoints enforce `expected_rp_id`, `expected_origin`, `require_user_verification=True`, and reject sign-count regressions as cloned-credential indicators. Challenges are stashed for 5 min in `step_up_verifications` and consumed on verify (one-shot). A successful authn ceremony emits a step-up proof (`record_step_up`). `backend/app/routes/webauthn_routes.py` exposes `/api/webauthn/{credentials, register/begin, register/verify, authenticate/begin, authenticate/verify}`; the verify endpoints return `503` unless `ENABLE_WEBAUTHN=1` so a half-deployed environment can never accidentally accept attestations against the wrong RP/origin.

### SEC-022 — No request-id correlation
- **Severity:** Medium · **Owner:** T5
- **Acceptance:** Middleware injects `X-Request-ID`; included in logs and audit events.

### SEC-023 — OAuth callback errors not audit-logged
- **Severity:** Medium · **Owner:** T5
- **Acceptance:** Audit event for every callback failure with IP/UA + reason.

### SEC-025 — No proof-of-identity on MFA reset
- **Severity:** Medium · **Owner:** T2
- **Acceptance:** Recovery-code use is OK; admin-driven resets require additional proof; rate-limited; audit-evented.
- **Closed:** 2026-04-19 (Task #11). MFA disable / reset endpoints are now wrapped in the `require_step_up()` dependency (`backend/app/security/step_up.py`), which demands a fresh password or WebAuthn re-auth within `STEP_UP_MAX_AGE_SECONDS` (default 5 min) and emits `mfa_reset_attempt` / `mfa_reset_success` audit events. Per-user rate-limit applied via `account_lockout`. Verified by `tests/test_security_hardening.py::test_step_up_required_for_mfa_reset`.

### SEC-026 — No rate limit on API-key validation itself
- **Severity:** Medium · **Owner:** T4 (limiter) + T2 (key surface)
- **Acceptance:** Per-IP rate limit on key-validation failures; alert on burst.

### SEC-027 — `last_used_at` write amplification on hot keys
- **Severity:** Medium · **Owner:** T2
- **Acceptance:** Batch updates (e.g. only every N seconds per key) or async sink.

### SEC-031 — GraphQL DoS via expensive resolvers
- **Severity:** Medium · **Owner:** T4
- **Acceptance:** Per-operation cost-based limit; slow-query log.

### SEC-032 — No per-socket throttling on Socket.IO
- **Severity:** Medium · **Owner:** T4
- **Acceptance:** Per-socket and per-user event-rate limits; tests.

### SEC-039 — File upload pipeline missing MIME sniff / size cap / AV-scan hook
- **Severity:** Medium · **Owner:** T4
- **Acceptance:** Hard size cap + MIME sniffing; AV-scan hook (clamav or vendor); random storage keys.

### SEC-041 — Privacy IP hash uses static low-entropy salt
- **Severity:** Medium · **Owner:** T6 (rotate salt) + T3 (vaulted secret)
- **Acceptance:** Rotate-able salt sourced from vault; periodic rotation policy.

### SEC-046 — Audit metadata is free-form (PII/secret leakage risk)
- **Severity:** Medium · **Owner:** T5
- **Acceptance:** Schema for metadata; required redaction; lint on emitter call sites.

### SEC-062 — Dockerfile not audited (digests / non-root / minimal base / scan)
- **Severity:** Medium · **Owner:** T7
- **Acceptance:** Pinned digests, non-root user, minimal base, image scan in CI, healthcheck.

### SEC-064 — No `security.txt` / `SECURITY.md` / responsible-disclosure surface
- **Severity:** Medium · **Owner:** T7
- **Acceptance:** Published `/.well-known/security.txt`, `SECURITY.md` with PGP key + contact + safe-harbor + scope + SLA.

### SEC-068 — No tabletop drill executed since runbook authored
- **Severity:** Medium · **Owner:** T5
- **Acceptance:** One full tabletop documented; lessons logged as follow-up findings.

---

## Low

### SEC-024 — Rate-limit fallback to per-process bucket on shared-backend errors
- **Severity:** Low · **Owner:** T2 + T5
- **Acceptance:** Documented degradation; alert when fallback occurs; SLO for shared backend availability.

### SEC-055 — Hardcoded test session secret in `TestSettings`
- **Severity:** Low · **Owner:** T3
- **Acceptance:** Generated per-run secret in test fixtures; `TestSettings` field becomes `Optional[str]` requiring explicit set.

---

## Summary counts

| Severity | Count |
|----------|-------|
| Critical | 7 |
| High | 35 |
| Medium | 16 |
| Low | 2 |
| **Total** | **60** |

Per-stream load:

| Stream | Owns | Notes |
|--------|------|-------|
| T2 (Identity, access & session) | SEC-003, SEC-007, SEC-008, SEC-009, SEC-010, SEC-011, SEC-014, SEC-016, SEC-017, SEC-018, SEC-025, SEC-026 (with T4), SEC-027, SEC-028, SEC-030 (with T4), SEC-053 (HIBP/MFA pieces), SEC-065, SEC-066 (with T5) | + share of SEC-012, SEC-024 |
| T3 (Data protection & secrets) | SEC-006, SEC-012 (key handling), SEC-019, SEC-049, SEC-050, SEC-051, SEC-052, SEC-053 (Postgres upgrade), SEC-054, SEC-055, SEC-056 (vault) | + crypto-shred used by T6 |
| T4 (Application surface) | SEC-001, SEC-002, SEC-004, SEC-005, SEC-013, SEC-015 (with T5), SEC-026 (with T2), SEC-029, SEC-030 (with T2), SEC-031, SEC-032, SEC-033, SEC-034, SEC-035, SEC-036, SEC-037, SEC-038, SEC-039, SEC-040, SEC-069 | Largest stream; SEC-069 is the trigger-event finding |
| T5 (Audit, monitoring & IR) | SEC-022, SEC-023, SEC-044, SEC-045, SEC-046, SEC-047, SEC-048, SEC-066 (with T2), SEC-067, SEC-068 | + SEC-024, SEC-052 cadence |
| T6 (Privacy & compliance) | SEC-041 (with T3), SEC-042, SEC-043, plus all policy/RoPA/DPA/DPIA/HIPAA program artifacts in COMPLIANCE_GAP_ANALYSIS.md | Largest doc volume |
| T7 (Supply chain & CI) | SEC-056 (scanner), SEC-057, SEC-058, SEC-059, SEC-060, SEC-061, SEC-062, SEC-063, SEC-064 | |

---

## How to use this backlog in the downstream streams

1. Each stream task starts by re-reading the findings assigned to it here. **Do not invent new scope** — if something is missing, file a new SEC-### with the same template and link it back.
2. When a finding closes, append a `Closed:` line with date, PR/commit, and verification evidence (test name, screenshot, log query). Do not delete entries.
3. If a finding is re-opened during pen-test or audit, mark it `Re-opened:` with date and reason; create a follow-up SEC-### only if scope changes.
4. Critical findings are deploy-blockers. CI should fail if any Critical SEC-### lacks a `Closed:` line **and** lacks an explicit, dated waiver from the security owner.

---

## Change control for SEC-### IDs and control status

This document is the single source of truth that downstream streams (T2–T7) consume. Drift between streams is the most common way security programs lose coherence. The following rules are mandatory:

1. **IDs are immutable.** Once a SEC-### is published in `main`, the number is permanent. Do not renumber, recycle, or delete IDs. If a finding turns out to be invalid, mark it `Status: Withdrawn` with a dated reason rather than deleting the row.
2. **Append-only history.** Every state change to a finding (close, reopen, severity change, owner reassignment, scope split) is appended as a dated entry under the row, not by editing prior text. Format: `YYYY-MM-DD — <action> — <commit/PR> — <reason>`.
3. **Splitting scope creates a new ID.** If a finding's scope grows mid-stream, file a new SEC-### whose description references the parent. Do not silently expand acceptance criteria of an existing finding.
4. **Reviewer required.** Changes to `FINDINGS_BACKLOG.md`, `THREAT_MODEL.md`, or `COMPLIANCE_GAP_ANALYSIS.md` require review by the security owner via CODEOWNERS (see SEC-058). PRs touching these files cannot be merged solely by their author.
5. **Status legend is canonical.** ✅/🟡/❌/➖ are the only allowed status markers in `COMPLIANCE_GAP_ANALYSIS.md`. Severity (`C`/`H`/`M`/`L`) is the only allowed marker here. Do not invent new states.
6. **Compliance-doc rows track this file.** When a SEC-### closes, every row in `COMPLIANCE_GAP_ANALYSIS.md` whose Findings column references it must be re-evaluated in the same PR. The PR description must list the controls re-evaluated and the resulting status delta.
7. **Trigger events update §1.** New incidents/pen-tests get a row in `INCIDENT_RESPONSE_RUNBOOK.md` and an updated debrief in `THREAT_MODEL.md` §1; any new findings they generate get the next free SEC-###.
8. **Quarterly verification.** Once per quarter, the security owner performs a baseline-verification pass: every Critical/High open finding is re-checked against the live system; Closed findings are spot-checked for regression; the resulting deltas are committed in a single PR.

---

## Task #16 progress — Supply chain, CI/CD & responsible disclosure (2026-04-19)

This section is the operational ledger for Task #16 (T7). Each row is anchored
to an existing SEC-### finding (immutable IDs per the change-control rules
above). Three brand-new follow-ups are introduced as SEC-070, SEC-071, SEC-072.

### Closures & state changes (2026-04-19)

- **SEC-056** — *No vault, no secret rotation playbook, no commit-time scanner enforced*
  - 2026-04-19 — partial-close — `docs/security/SECRET_ROTATION.md` published with the inventory, rotation cadence, emergency procedure, personnel-change procedure, PGP ceremony, and attestation template. Pre-commit gitleaks already enforced (`.pre-commit-config.yaml`). **Remaining:** centralized vault (1Password Connect or HashiCorp Vault) — kept open, severity unchanged.

- **SEC-057** — *No SBOM / SLSA build provenance / signed releases* — **CLOSED 2026-04-19**
  - 2026-04-19 — partial-close — `docs/security/RELEASE_PLAYBOOK.md` and `docs/security/SLSA_PROVENANCE.md` define the tagging, signing (Sigstore keyless), SLSA L3 generator wiring, SBOM generation (CycloneDX) and verification recipe. CI workflow `.github/workflows/security.yml` job `sbom` now produces CycloneDX SBOMs on every PR / push.
  - 2026-04-19 — partial-close (cont.) — `.github/workflows/release.yml` published. On every signed `vX.Y.Z` tag it: (1) re-runs the security baseline against the tag SHA and verifies tag PGP signature; (2) builds + pushes the backend container to ghcr; (3) signs the image with Sigstore Cosign keyless; (4) generates SLSA v1.0 build provenance via `actions/attest-build-provenance` and pushes it as an OCI attestation; (5) generates a CycloneDX SBOM with Syft and attaches it both as an OCI attestation and a release artifact; (6) runs `cosign verify` + `cosign verify-attestation` end-to-end before publishing the GitHub Release.
  - 2026-04-19 — **close (Task #27)** — release.yml now also: (7) builds the **frontend** asset bundle with `npm ci && vite build` (lockfile-fidelity enforced by SEC-074 drift gate), (8) packs it as a reproducible tarball whose sha256 is the supply-chain identity, (9) signs it as a Sigstore blob (`cosign sign-blob`) keyless with `.sig` + `.pem` published as release assets, (10) attests SLSA v1.0 provenance against the tarball digest, (11) generates a frontend CycloneDX SBOM via Syft, and (12) runs a `deploy-production` job gated on the `production` GitHub Environment (two human approvers + short-lived OIDC-federated cloud creds per `BRANCH_PROTECTION.md` §4.1) that re-verifies cosign signature + SBOM attestation + SLSA provenance for **both** artifacts before any deploy step runs. Note on attestor choice: we use `actions/attest-build-provenance` instead of `slsa-framework/slsa-github-generator` — both produce SLSA v1.0 in-toto attestations with the same builder identity, and the GitHub-native attestor reduces the pinned external workflow surface (SEC-073). Long-term Rekor mirroring remains open as SEC-072; cloud deploy-step wiring blocked on SEC-063 (OIDC-federated cloud creds).

- **SEC-058** — *Branch protection / signed-commit enforcement unverified; no CODEOWNERS*
  - 2026-04-19 — partial-close — `.github/CODEOWNERS` published covering CI, lockfiles, security-sensitive code, privacy/legal surfaces, and disclosure files. `docs/security/BRANCH_PROTECTION.md` is the settings-as-code baseline.
  - 2026-04-19 — partial-close (cont.) — `.github/workflows/governance-verify.yml` (now implemented, see SEC-070) provides daily drift detection: required-check name lint, gate-flip schedule lint, tag-only `uses:` lint, and an advisory live ruleset snapshot. **Remaining:** apply the documented ruleset on the live GitHub repo (UI/Terraform), and flip the live ruleset diff from advisory to blocking on `2026-08-02`; kept open.

- **SEC-059** — *Dependency vulnerability gate not confirmed enforced*
  - 2026-04-19 — partial-close — `.github/workflows/security.yml` runs `pip-audit`, `npm audit`, and `osv-scanner` on every push, PR, and daily schedule. `.github/dependabot.yml` adds `github-actions` and `docker` ecosystems and groups patch/minor + security updates. Currently **advisory** (`continue-on-error: true`); flips to blocking per §gate-flip-schedule below.
  - 2026-04-24 — paging wired (Task #37) — `security.yml::pager` now mirrors the `governance-verify` paging pattern: it inspects `needs.<scanner>.result` for `python-sca` / `frontend-sca` / `license-scan` (alongside the SAST + container scanners), opens or refreshes a single `security-scan-failure` GitHub issue, and POSTs one PagerDuty Events v2 (or generic) page **per failed scanner** with a stable `dedup_key = security.yml/<scanner>/<owner>/<repo>` so an overnight HIGH+ CVE pages on-call instead of waiting for the next PR's required-check to go red. Auto-resolves on the next green default-branch run. Wiring + ack/resolve + drill in `INCIDENT_RESPONSE_RUNBOOK.md` §"Scanner-failure paging".

- **SEC-060** — *Commit-time + CI secret scanner not verified*
  - 2026-04-19 — closed — gitleaks runs both pre-commit (`.pre-commit-config.yaml`) and CI (`security.yml::secret-scan`, full-history scan with `fetch-depth: 0`). GitHub push-protection enabled at the org level (see `BRANCH_PROTECTION.md` §3).

- **SEC-061** — *No SAST gate*
  - 2026-04-19 — partial-close — `security.yml` runs Bandit + Semgrep (Python: `p/python`, `p/owasp-top-ten`, `p/security-audit`, `p/secrets`) and Semgrep (TS/React: `p/typescript`, `p/react`, `p/javascript`, `p/owasp-top-ten`, `p/xss`). All findings upload to GitHub code scanning as SARIF. Currently **advisory**; flips to blocking per §gate-flip-schedule.
  - 2026-04-24 — paging wired (Task #37) — `security.yml::pager` covers `python-sast` and `frontend-sast` with stable per-scanner `dedup_key`s (`security.yml/python-sast/<owner>/<repo>`, `security.yml/frontend-sast/<owner>/<repo>`), so a Bandit/Semgrep/ESLint HIGH+ regression pages on-call once the gate flips. See `INCIDENT_RESPONSE_RUNBOOK.md` §"Scanner-failure paging".

- **SEC-062** — *Dockerfile not audited (digests / non-root / minimal base / scan)*
  - 2026-04-19 — close — `backend/Dockerfile` rewritten as a multi-stage build with: digest-pinned base (`python:3.13-slim-bookworm@sha256:061b6e52a07ab675f0e4a9428c5a8ee6bed996983427f4691f6bebf29c56d9dc` on both stages), non-root `app` user (uid 10001), `tini` PID 1, `HEALTHCHECK` against `/ping`, env-controlled forwarded-allow-ips (default `127.0.0.1`), `--no-install-recommends` + cache cleanup, OCI labels for provenance, dropped privileges before `CMD`. CI runs Hadolint + Trivy (`security.yml::container-scan`) on every PR; release workflow runs Cosign sign + SLSA provenance + SBOM attestation per SEC-057.
  - 2026-04-24 — paging wired (Task #37) — `security.yml::pager` covers `container-scan` with `dedup_key = security.yml/container-scan/<owner>/<repo>`; a new HIGH+ image CVE or Hadolint regression pages on-call once the gate flips per §gate-flip-schedule. See `INCIDENT_RESPONSE_RUNBOOK.md` §"Scanner-failure paging".

- **SEC-063** — *CI assumed to use long-lived cloud creds*
  - 2026-04-19 — open, scoped — `BRANCH_PROTECTION.md` §4 mandates short-lived OIDC-federated cloud credentials for the `production`/`beta` environments. **Remaining:** wire the actual cloud trust policy + remove any long-lived AWS/GCP keys from repo secrets; tracked in this row until the deploy workflow lands.

- **SEC-064** — *No `security.txt` / `SECURITY.md` / responsible-disclosure surface*
  - 2026-04-19 — closed — `SECURITY.md` (full coordinated-disclosure policy with safe-harbor, scope, SLA, PGP scaffold, recognition), `/.well-known/security.txt` (RFC 9116 at repo root), `frontend/public/.well-known/security.txt` (SPA copy), and `docs/security/HALL_OF_FAME.md` published. PGP key publication tracked separately in `SECRET_ROTATION.md` §6.

### New follow-up findings introduced by Task #16

### SEC-070 — No scripted verifier for branch-protection drift
- **Severity:** Medium · **Owner:** T7 · **Surface:** repo settings + CI.
- **What:** `BRANCH_PROTECTION.md` is the canonical baseline, but verification was a quarterly manual diff. Drift between the doc and live ruleset is the most common cause of silent control regressions.
- **2026-04-19 — partial-close** — `.github/workflows/governance-verify.yml` (daily 07:00 UTC + workflow_dispatch) is **implemented and running** with three blocking lints: (1) tag-only `uses:` lint (SEC-073), (2) required-check name lint that walks every workflow's top-level `name:` and `jobs.<id>.name:` and diffs against `BRANCH_PROTECTION.md` §1.2 (catches the silent-disable bug on rename), (3) gate-flip schedule lint that fails if any gate in `FINDINGS_BACKLOG.md` is >14d past its flip date. It also snapshots the live ruleset via `gh api` for diffing — this snapshot stays advisory until one full quarter of clean snapshots accumulates and the comparison schema is locked.
- **2026-04-24 — close (Task #28)** — `governance-verify.yml` now also runs (4) a **gate-CoE-matches-schedule** lint that pairs every `continue-on-error: true # remove to flip to blocking (SEC-###)` marker in `security.yml` against the gate-flip table and fails if a marker survives past its flip date (catches the inverse of the date-only lint: a row whose flip date is in the past but whose advisory marker was never removed), and (5) a **structured live-ruleset diff** that resolves every branch ruleset via `gh api repos/.../rulesets/{id}`, picks the one targeting `refs/heads/main`, and asserts: `enforcement=active`, `pull_request.required_approving_review_count=2`, `dismiss_stale_reviews_on_push`/`require_code_owner_review`/`require_last_push_approval`/`required_review_thread_resolution` all true, every check in §1.2 is present in `required_status_checks`, and the `non_fast_forward`/`deletion`/`required_linear_history`/`required_signatures` rules exist (§1.3). The diff stays advisory until `2026-08-02` per the gate-flip table. Drift in any of these five lints triggers the new **`Open / refresh security-drift tracking issue`** step, which de-dupes by reusing any existing open `security-drift` issue (creating the label first if needed) and optionally POSTs to `secrets.SECURITY_PAGER_WEBHOOK` for off-platform paging.
- **2026-04-24 — paging wired (Task #36)** — `governance-verify.yml` now ships the paging payload in two shapes: PagerDuty Events API v2 (when both `SECURITY_PAGER_WEBHOOK` and the new `SECURITY_PAGER_ROUTING_KEY` secrets are set, with `event_action:trigger` + a stable `dedup_key = governance-verify/security-drift/<owner>/<repo>` that mirrors the single-open-issue convention) and the legacy generic shape for Opsgenie/Slack/custom receivers (when only `SECURITY_PAGER_WEBHOOK` is set). A new `Auto-resolve security-drift page on green run` step closes the tracking issue **and** posts `event_action:resolve` (PD only) on the next green run, so on-call no longer holds a stale incident after a fix lands. The full wiring + ack/resolve + drill procedure is documented in `docs/security/INCIDENT_RESPONSE_RUNBOOK.md` §"Security-drift paging".
- **Remaining:** (1) populate `SECURITY_PAGER_WEBHOOK` (and `SECURITY_PAGER_ROUTING_KEY` if PagerDuty) on the live repo once the security on-call rotation is formalised — code/runbook are ready, this is a one-time secret-set per the runbook §"Wiring the on-call pager"; (2) apply the documented ruleset on the live GitHub repo so the now-blocking diff has something to verify against, then flip the live-ruleset-diff lint from advisory to blocking on `2026-08-02`. Kept open at lower severity.
  - 2026-04-24 — applier landed (Task #35) — `scripts/apply_branch_protection.py` parses §1.2 of `BRANCH_PROTECTION.md` with the same regex the verifier uses and POSTs/PUTs the documented ruleset via `gh api` (idempotent, named `main-branch-protection`). Dry-run verified locally; **execution against the live `Manifest-Startup/Manifest` repo still pending** because it requires repo-admin GitHub credentials that are not available from the codebase environment. Operator runbook is in `BRANCH_PROTECTION.md` §6. Once executed and the daily `Live ruleset diff vs. BRANCH_PROTECTION.md` step reports zero findings, capture that run URL in the next access-review minutes and proceed with the `2026-08-02` flip.

### SEC-071 — No quarterly transparency report for release artifacts
- **Severity:** Low · **Owner:** T7 · **Surface:** trust center.
- **What:** Customers have no easy way to enumerate every released artifact's digest + provenance link. Trust-center transparency reports are table stakes for SOC 2 / customer security questionnaires.
- **Acceptance:** Quarterly markdown report under `docs/security/transparency/<YYYY-Qn>.md` listing each release tag, artifact digests, builder identity, provenance URL, and SBOM URL. Linked from `https://manifeststartup.com/trust`.

### SEC-072 — SLSA provenance not mirrored to a tamper-evident long-term store
- **Severity:** Low · **Owner:** T7 · **Surface:** Sigstore Rekor / mirror.
- **What:** Sigstore Rekor entries are immutable, but a 7-year SOC 2 retention requires us to also self-archive the provenance bundles (Rekor history compaction is theoretical, not actual, but auditors prefer a vendor-independent copy).
- **Acceptance:** Release workflow uploads the DSSE-wrapped provenance bundles to a write-once cloud-storage bucket (object-lock enabled, 7-year retention). Quarterly verification job re-checks Rekor inclusion proofs against the archived bundles.

### Gate-flip schedule (advisory → blocking)

The CI security gates start in advisory mode (`continue-on-error: true`) so we can baseline existing findings without blocking developer flow. Each gate flips on the date below; flipping is a one-line change in `.github/workflows/security.yml` plus the corresponding row update here.

| Gate                                       | Owning finding | First green required by | Flip-to-blocking by |
| ------------------------------------------ | -------------- | ----------------------- | ------------------- |
| `secret-scan` (gitleaks CI)                | SEC-060        | already green           | **already blocking** (pre-commit gates locally) |
| `python-sast` (bandit HIGH+ + semgrep ERROR) | SEC-061      | 2026-05-03              | 2026-06-19          |
| `frontend-sast` (semgrep ERROR)            | SEC-061        | 2026-05-03              | 2026-06-19          |
| `python-sca` (pip-audit HIGH+ CVE)         | SEC-059        | 2026-05-03              | 2026-06-19          |
| `frontend-sca` (npm audit HIGH+ + osv HIGH+) | SEC-059      | 2026-05-03              | 2026-06-19          |
| `license-scan` (disallowed license)        | SEC-059        | 2026-05-17              | 2026-06-19          |
| `container-scan` (trivy HIGH+, hadolint error) | SEC-062    | 2026-05-17              | 2026-06-19          |
| `sbom`                                     | SEC-057        | always uploaded         | n/a (artifact only) |
| `release.yml` (cosign + provenance + SBOM) | SEC-057        | first signed `vX.Y.Z` tag | **already blocking** (release fails closed if `cosign verify` or attest fails) |
| `governance-verify::tag-only-uses-lint`    | SEC-073        | already green           | **already blocking** (job fails on tag-only `uses:` in security-critical workflows) |
| `governance-verify::required-check-lint`   | SEC-058/SEC-070 | already green          | **already blocking** |
| `governance-verify::gate-flip-lint`        | SEC-070        | always green within 14d window | **already blocking** |
| `governance-verify::live-ruleset-diff`     | SEC-070        | 2026-07-19              | 2026-08-02          |

A gate that misses its flip date by **>14 days** becomes a Critical finding under the owning SEC-### until either flipped or formally waived by the security owner with a dated rationale.

**2026-05-20 — flip-date extension (SEC-061 + SEC-059 PR/CI gates).** The two pairs above (`python-sast`, `frontend-sast`, `python-sca`, `frontend-sca`) were originally scheduled to flip 2026-05-19. Dates pushed to **2026-06-19** to align with the `license-scan` / `container-scan` cohort and give time to baseline the remaining advisory findings (bandit 0 HIGH locally; semgrep + osv-scanner / npm-audit need a clean first-green run after the 2026-05-20 dependency bumps in `dbd581ae`).

### Counts after 2026-04-19 closures

(Re-run §"Count summary" at next quarterly verification.)

### SEC-074 — Lockfile drift not enforced in CI
- **Severity:** Medium · **Owner:** T7 · **Surface:** `.github/workflows/security.yml`.
- **What:** A drifted lockfile (`requirements.txt`/`package-lock.json` out of sync with `package.json` or with the actual resolver result) silently invalidates every downstream scan by changing the installed graph. The audit/SBOM/license output describes a graph that does not match what runs in production.
- **2026-04-19 — close** — `.github/workflows/security.yml::lockfile-drift` runs on every push, PR, and daily schedule. Backend uses `pip install --no-deps -r backend/requirements.txt && pip check` (fails on broken/conflicting constraints). Frontend uses `npm ci` in `frontend/` (fails non-zero if `package.json` and `package-lock.json` disagree). Job is **already blocking** — drift here breaks the whole reproducibility chain so it is not appropriate to keep advisory.

### SEC-073 — GitHub Actions and base container images not pinned by SHA / digest
- **Severity:** Medium · **Owner:** T7 · **Surface:** `.github/workflows/*`, `backend/Dockerfile`.
- **What:** Workflow steps reference third-party actions by tag (`@v4`, `@v3`, `@0.24.0`, …) and the backend Dockerfile uses `python:3.13-slim-bookworm` by tag, not by `@sha256:` digest. Tag references are mutable: an attacker (or compromised maintainer) can repoint a tag to a malicious commit, as happened with the tj-actions/changed-files compromise. Digest pinning eliminates the class.
- **2026-04-19 — partial-close** —
  - Every third-party `uses:` in `.github/workflows/security.yml`, `.github/workflows/release.yml`, and `.github/workflows/governance-verify.yml` is now pinned to a 40-char commit SHA with the human-readable tag in a trailing comment (actions/checkout, setup-python, setup-node, upload-artifact, download-artifact, codeql-action/upload-sarif, gitleaks-action, osv-scanner-action, hadolint-action, trivy-action, cosign-installer, attest-build-provenance, docker/setup-buildx-action).
  - `backend/Dockerfile` both `FROM` lines pin to `python:3.13-slim-bookworm@sha256:061b6e52a07ab675f0e4a9428c5a8ee6bed996983427f4691f6bebf29c56d9dc`.
  - `.github/dependabot.yml` already runs the `github-actions` + `docker` ecosystems weekly; @Manifest-Startup/security reviews the SHA bumps per CODEOWNERS.
  - `.github/workflows/governance-verify.yml::Tag-only \`uses:\` lint` fails the daily build if any `uses:` in the security-critical workflows drops back to a tag-only reference.
- **2026-04-24 — close (Task #26)** —
  - Every third-party `uses:` in the legacy workflows `.github/workflows/main.yml` (8× checkout@v3, 6× setup-python@v4, 5× setup-node@v3, 1× cypress-io/github-action@v6), `.github/workflows/survey-feedback.yml` and `.github/workflows/website-testing.yml` (checkout@v4, setup-python@v5, upload-artifact@v4) is now pinned to a 40-char commit SHA with the version tag in a trailing comment. SHAs were resolved live against the GitHub API at pin time.
  - `frontend/dockerfile` `FROM` line is now pinned (`node:18-bookworm-slim@sha256:f9ab18e354e6855ae56ef2b290dd225c1e51a564f87584b9bd21dd651838830e`); `backend/Dockerfile` was already digest-pinned per the partial-close above.
  - `.github/workflows/governance-verify.yml::Tag-only \`uses:\` lint` now scopes to **all** `.github/workflows/*.yml` (no carve-out) and is joined by a sibling **Docker base-image digest-pin lint** that walks every tracked Dockerfile (`git ls-files '*[Dd]ockerfile' '*[Dd]ockerfile.*' '*.dockerfile'`) and fails on any `FROM` line missing `@sha256:` (stage-aliasing `FROM <stage> AS …` is excluded). Both lints fail the daily 07:00 UTC governance run if any new workflow or Dockerfile regresses.
  - Authoritative scope of SEC-073 is now closed; refresh stays automated through `.github/dependabot.yml`'s `github-actions` + `docker` ecosystems with @Manifest-Startup/security review per CODEOWNERS.
