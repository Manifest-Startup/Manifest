# Edge Worker — agent guide (child of [`../../AGENTS.md`](../../AGENTS.md))

The single production entry point (`manifest-production` Worker). It serves the built frontend from static assets and proxies backend paths (`/graphql`, `/api/*`, discovery documents, media) to `BACKEND_ORIGIN`, the FastAPI Docker image on Render. Switching backend host means changing `BACKEND_ORIGIN` only.

- `src/index.mjs` routes requests; `src/edge.mjs` holds the proxy and asset logic; `src/mcp*.mjs` serves the public MCP surface; `src/ora-reporting.mjs` handles agent-readiness reporting.
- `wrangler.jsonc` holds vars and routes. `EDGE_SHARED_SECRET` is a secret (`wrangler secret put`) and must match the backend so the origin only accepts edge traffic. Never commit its value.
- Preserve backend routing and static-asset behaviour; add a case to `tests/edge.test.mjs` for every new route.
- One production Worker per project; no versioned copies (`cloudflare-deployment-hygiene` skill).

```bash
npm test                         # node --test tests/*.test.mjs
npx wrangler deploy --dry-run    # bundle check; real deploys only when explicitly asked
```
