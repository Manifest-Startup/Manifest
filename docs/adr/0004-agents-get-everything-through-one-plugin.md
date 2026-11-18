# 0004. Agents get everything through one plugin, generated from the schema

- Status: Accepted (2026-11-17). Builds on [0002](0002-open-media-is-the-only-sign-in.md) and [0003](0003-manifest-cli-browser-login.md).
- Plugin: [`agent-plugin/`](../../agent-plugin/README.md) · Tools: [`agent-plugin/TOOLS.md`](../../agent-plugin/TOOLS.md)

## Context

Agents could only reach a small API-key surface (`/mcp`: 7 tools over `/api/v1`), while people use about 100 GraphQL operations plus account REST routes. The CLI (0003) already proved that generating commands from the schema keeps them complete. Agent hosts now install plugins from several catalogs (Claude Code, Codex, Cursor, VS Code, Gemini CLI, Antigravity, the MCP Registry, Claude and ChatGPT connectors), and all of them can sign in to a remote MCP server with OAuth.

## Decision

**Everything is a plugin, and the schema is its source.**

- **Tools are generated.** `scripts/generate_agent_tools.py` turns `manifest_cli/catalog.json` (GraphQL, itself generated) and `manifest_cli/rest.py` into `deploy/cloudflare/src/mcp-tools.generated.json` and `agent-plugin/TOOLS.md`: JSON Schema inputs, MCP annotations (read-only, destructive, idempotent, open-world), and the GraphQL document or REST route to call. Default selections drop credential fields (tokens, secrets, keys). An explicit `EXCLUDED` map lists the few operations agents don't get (guest sessions, logging out their own session, the realtime credential, saving an OpenAI key, raw-token integration connects, the legacy background-task trigger, file upload), each with the reason the agent can relay.
- **One server, two credentials.** The edge Worker serves `/mcp`. An API key (`manifest_sk_…`) keeps the original 7 tools; any other bearer token is a Manifest session and gets every generated tool, forwarded to `/graphql` or the REST route with that same token, so backend permission checks apply unchanged. No token → `401` with `WWW-Authenticate: Bearer resource_metadata=…` so clients start OAuth. Destructive tools take `confirm`; without `confirm: true` the Worker returns a preview and never calls the backend.
- **OAuth 2.1 on the backend** (`app/services/identity/agent_oauth.py`, `app/routes/agent_oauth_routes.py`): RFC 9728 and RFC 8414 discovery; clients via Client ID Metadata Documents (fetched through `safe_http`) or stateless RFC 7591 registration (the `client_id` is the HMAC-signed metadata, so there is no table); authorization code + PKCE S256 only; redirects are https, loopback http (any port, RFC 8252) or private-use app schemes; RFC 8707 `resource` must be `/mcp`. The approval page reuses the CLI's rules: signed-in non-guest person, Open Media sign-in within 5 minutes, HMAC-bound Allow link. Codes reuse the CLI code machinery with their own audience and are bound to the client.
- **Tokens are sessions.** Access tokens are session JWTs with `kind: "agent"` (24 hours) on a `user_sessions` row labelled `AI agent · <client>`, listed and revocable under Account → Security; they share the CLI's 14-day idle window. Refresh tokens are signed, bound to the client and the session; a refresh revokes the old session and mints a new one, so a replayed refresh token fails. `POST /api/oauth/revoke` implements RFC 7009.
- **One plugin folder, many catalogs**, the same layout as Open Media's ADR 0027: `.claude-plugin/`, `.codex-plugin/`, `.antigravity-plugin/`, Agent Plugins `plugin.json` + `mcp.json`, `registry/manifest.server.json`, root `gemini-extension.json`, and root marketplaces. Eight skills and seven commands are the only hand-written agent guidance.
- **Guards.** `scripts/check.py` area `plugin` fails when generated tools are stale, when any tool isn't taught by a skill, when a skill or command names a missing tool, when an operation is neither a tool nor excluded, or when manifests disagree on name, version or server URL.

## Consequences

- A new GraphQL field becomes an agent tool by regenerating two files; `check.py` refuses to let it ship untaught.
- Agents can do destructive things (erase account, revoke sessions, invest). Mitigations: confirm-twice in the server, MCP destructive hints for hosts, fresh sign-in to connect, step-up still enforced by the backend for its sensitive routes, and every agent visible and revocable.
- Resolvers without docstrings produced weak tool descriptions; 44 docstrings were added, and new resolvers should have one.
- The MCP Registry name `com.manifeststartup/manifest` needs DNS verification by the owner before publishing; marketplace submissions are owner actions.
- Render's free tier cold-starts the backend; `initialize` and `tools/list` are answered by the Worker, so only tool calls wait.
