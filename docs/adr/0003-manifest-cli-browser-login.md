# 0003. The Manifest CLI signs in through the browser and is generated from the schema

- Status: Accepted (2026-11-15). Builds on [0002](0002-open-media-is-the-only-sign-in.md) (Open Media is the only sign-in).
- Guide: [CLI.md](../CLI.md) · API: [API.md](../API.md#manifest-cli-sign-in-rest-browser--cli)

## Context

People and agents want to do everything Manifest does from a terminal. Manifest has no passwords (0002), so the CLI cannot prompt for credentials, and API keys only cover the small `/api/v1` surface. The product lives in GraphQL (about 100 queries and mutations), and production disables introspection, so a CLI cannot discover the schema at run time. A hand-written CLI would drift from the API within weeks.

## Decision

- **Package.** The `manifest` console script lives in the existing `manifest-mcp` distribution as a sibling package, `mcp_server/src/manifest_cli`. It reuses `manifest_mcp.client.ManifestClient` (httpx; now with `request()`, `graphql()`, a custom `transport` and `user_agent`), adds no dependencies, and installs with the same `pip install -e mcp_server`. `manifest_mcp` now imports its server lazily so the CLI does not load the MCP SDK. `manifest-dev` (repo scripts) is unrelated.
- **Login = loopback + PKCE, approved in the browser** (`backend/app/routes/cli_auth_routes.py`, `app/services/identity/cli_auth.py`):
  - `manifest login` listens on `http://127.0.0.1:<random port>/callback` and opens `GET /api/cli/authorize?redirect_uri&state&code_challenge&code_challenge_method=S256`. Only `http://127.0.0.1|localhost:<port>/callback` is accepted; bad requests get an error page, never a redirect.
  - Without a signed-in, non-guest browser session the route sends the browser to `/login?next=…`, i.e. Continue with Open Media, so passkeys and MFA apply. `safe_next` allows exactly this one backend path. The login page now honours `?next=`.
  - The page "Allow Manifest CLI on this computer?" (login-page styling, `no-store`, `X-Frame-Options: DENY`) has an **Allow** link carrying an HMAC bound to the browser session and the request, so it cannot be forged cross-site. It is a link, not a form, because the CSP's `form-action 'self'` would block a form's redirect to the loopback address.
  - The one-time code is a 2-minute JWT signed with a key derived from `SESSION_SECRET` with its own audience (never usable as a session), bound to the redirect URI and the PKCE challenge. Its `jti` is spent in the shared cache (Redis when configured), so it works once and across restarts without a table.
  - `POST /api/cli/token {code, code_verifier, redirect_uri, hostname}` verifies all of that, refuses guests and codes whose approving browser session has since been signed out, and mints a normal Manifest session JWT with `kind: "cli"`: 30 days (`CLI_SESSION_TTL_DAYS`), 14-day idle timeout (`CLI_SESSION_IDLE_TIMEOUT_SECONDS`), `auth_iat` copied from the browser session (a CLI token is never a "fresher" sign-in than the person's). It is a `user_sessions` row labelled `Manifest CLI · <hostname>` in `user_agent` (not overwritten on use), so it appears in Account → Security → Active sessions (`SessionInfo.kind = "cli"`) and can be revoked there. Audit event `cli_session_created`.
  - There is no refresh token: when the session expires, run `manifest login` again. `manifest logout` calls `POST /api/auth/logout` with the bearer token, which revokes that session. The token is stored in `~/.config/manifest/cli.json` (0600, directory 0700) with the `base_url`.
- **Commands are generated.** `scripts/generate_cli_catalog.py` loads the Strawberry schema and writes `manifest_cli/catalog.json`: every query and mutation (kebab-case command), its arguments and types, input objects and enums, a default selection (scalar fields to depth 2), a destructive flag (delete, remove, revoke, invest, contribution, payment, disconnect, restore, logout, publish, role changes) and a hash of the SDL. `scripts/check.py` (area `cli`) and `tests/tooling/test_cli_catalog.py` fail when the committed catalog differs, so every schema change ships with a regenerated CLI.
- **REST** areas without GraphQL equivalents (API keys and clients, usage and tiers, privacy consent, DSAR, profile picture upload, GitHub bootstrap, voice capabilities, trust center) are hand-listed in `manifest_cli/rest.py`; `manifest api <METHOD> <path>` and `manifest graphql '<document>'` reach everything else.

## Consequences

- The CLI covers the whole GraphQL surface on day one and cannot silently fall behind it; the cost is one regeneration command per schema change.
- No migration: CLI sessions reuse `user_sessions` (`user_agent` holds the label; `kind` is derived from it for display and taken from the signed JWT for enforcement).
- A stolen CLI token works for up to 30 days unless revoked, longer than a browser session; it is revocable from the Account page, by `revokeOtherAccountSessions`, and by SCIM deprovisioning. Step-up routes (API key create/rotate/revoke, DSAR erase/rectify) still need a sign-in within 5 minutes: run `manifest login` again first.
- Commands with no resolver docstring get a generic description; adding a docstring or `strawberry.field(description=…)` improves `--help` after regeneration.
- `/api/v1` (API-key) routes are not CLI commands; use `manifest api` with `MANIFEST_API_TOKEN` set to the key, or the MCP server.
