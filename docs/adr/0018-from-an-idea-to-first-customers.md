# 0018. From an idea to first customers, in the conversation

- Status: Proposed (2026-11-21).
- Code: `backend/app/services/ideas/customer_discovery.py` (the flow, scoring, note), `backend/app/services/integrations/discovery_connectors.py` (capabilities and providers), `backend/app/graphql/resolvers/discovery.py`, `types/discovery.py`; voice: `services/voice/live/bot.py` (prompt, activity summary), `tools.py` (core tools, labels, clipping); plugin: `agent-plugin/skills/manifest-customers/`, `commands/customers.md`; Gmail: `routes/oauth_routes.py` provider `gmail`, `frontend/src/features/account/lib/integrationsCatalog.ts`.

## Context

Founders want to know whether anyone needs their idea and who to talk to first. Manifest already had the pieces: voice and agents that reach every GraphQL field through one generated catalog, grounded web search on the person's own OpenAI key (`AIRouter.web_search_json`, with citations), the cost-tracked agent pattern of partner discovery, OAuth integrations with encrypted tokens, and an account vault for notes. The product rule was no new screens, tabs, dashboards or wizards.

## Decision

- **Six GraphQL fields, no new UI.** `customerDiscovery` (read), `researchMarket`, `findProspects`, `excludeProspects`, `draftOutreach`, `createOutreachEmailDrafts`, plus `saveCustomerDiscovery` for agents and `discoveryCapabilities`. The generated catalog puts them in voice, `/mcp`, the plugin and the CLI at once. Voice sees the four everyday ones directly; its prompt makes the flow a conversation (research while the founder talks, offer five customers when the direction is clear, one question at a time, summaries aloud, no lists or URLs read out). Results show in the existing voice activity line ("5 prospects: …") and in the person's notes.
- **State is a note in the person's vault.** `Notes/Customer discovery/<idea>.md` holds the readable report (sources linked, hypotheses marked) and, in a trailing HTML comment, the structured state. No table or migration; it syncs to the person's computers like every note, and research under a week old is reused (`refresh` redoes it).
- **Capabilities, not vendors.** `web.search` (OpenAI search models, BYOK), `web.read` (`safe_http`, text fenced as untrusted), `prospects.search`/`prospects.enrich` (Apollo.io with a server `APOLLO_API_KEY`, else web search), `email.createDraft`/`email.getDraft` (Gmail, `gmail.compose`). There is no `email.send`: Manifest prepares, the founder sends. `discoveryCapabilities` says what works and how to enable the rest.
- **Trust is enforced in code, not only in prompts.** Findings without a source become hypotheses; the business model, ideal customer profile and pricing are always hypotheses. A prospect without any source URL is dropped, a website that doesn't answer drops a web-search prospect, an unsourced decision-maker is removed, and an email becomes a recipient only when it is verified (a provider or a cited public page). The score is computed server-side from the brief's weights (35/25/20/10/10); evidence of need is 0 without a sourced item and contactability comes from what was actually found. Each prospect lists what is still unverified.
- **Asking before Gmail.** `createOutreachEmailDrafts` is destructive in the catalog, so voice, MCP and the plugin show a preview and need `confirm: true`. Drafts already saved are never duplicated; edited emails get a new draft.
- **No key? The person's agent does the research.** Like the document guides (ADR 0005), an agent with its own web search (Claude Code behind the voice bridge, Codex) researches and calls `saveCustomerDiscovery`; the same normalisation, website checks and scoring apply.
- **Demo data is never saved.** `findProspects(demo: true)` at the service level returns fictional `example.com` agencies labelled "(demo)"; it is not exposed as a tool argument.

## Consequences

- Research and prospect steps run synchronously inside the request (about a minute each); the voice tool timeout is 95 s to stay under the edge proxy's 100 s. There is no durable background job yet, so a step that outlives the session is lost and must be re-asked.
- Renaming an idea starts a new note (the path follows the title).
- Gmail needs `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` on the server and `/auth/gmail/callback` as an authorised redirect URI; Apollo needs `APOLLO_API_KEY`. Neither is set in production yet.
- Search-model JSON can still contain a wrong URL; checks catch dead sites, not wrong claims, so the note keeps every source next to its claim for the founder to verify.
