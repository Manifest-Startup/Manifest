# 0021. One memory for every agent, kept as files in the vault

- Status: Accepted (2026-11-22).
- Code: `backend/app/services/memory/store.py` (files, recall, dedup, conversations, extraction), GraphQL `recall`, `memories`, `remember`, `updateMemory`, `forgetMemory`, `saveVoiceConversation` in `backend/app/graphql/resolvers/memory.py` / `types/memory.py`; hosted voice: `services/voice/live/bot.py` (`remembered`, prompt) and `tools.py` (core tools); local voice: `mcp_server/src/manifest_cli/agents.py` (`VOICE_STYLE`, `WRAP_UP`) and `bridge.py` (`describe_memory`, `POST /voice/wrap-up`); app: `frontend/src/features/voice/voiceMemory.ts`, `useConversationMemory.ts`, `features/memory/` (Remembered card, Account → Memory); agents: `agent-plugin/skills/manifest-memory/SKILL.md`, the rule in `skills/manifest/SKILL.md`, `CONTEXT.md` and the `/mcp` instructions (`deploy/cloudflare/src/mcp-account.mjs`). Tests: `backend/tests/test_memory.py`, `mcp_server/tests/test_voice_bridge.py`, `frontend/src/features/memory/__tests__/memory.test.tsx`, `tests/tooling/test_agent_plugin.py::test_every_agent_is_told_to_use_manifest_memory`.

## Context

People talk to Manifest by voice and through their own agents (Claude Code, Codex, Cursor, Gemini CLI). Each agent had its own memory, or none, so a decision made by voice yesterday was unknown to Codex today. The owner asked for one memory any agent can pick up, with a seamless experience. Hosted memory services (mem0 and similar) would send personal conversations to another company, add a key and a bill, and reach only agents that integrate them.

## Decision

- **The vault is the store.** Each memory is one Markdown file in `vault_files` (ADR 0007): `Memory/<idea>/<fact>.md` or `Memory/General/…`, with front matter (`memory_id`, `kind`, `idea`, `idea_id`, `source`, `conversation`, `created`, `updated`) and the fact as the body. Voice conversations are `Conversations/<date time> Voice – <idea>.md`, linked to the idea and to what was remembered. They sync to every computer, can be read and edited in Obsidian, and stay private to their owner (never shared with collaborators). No new table, service or key.
- **Same operations everywhere.** `remember`, `recall`, `forgetMemory`, `updateMemory`, `memories` and `saveVoiceConversation` reach `/mcp`, the plugin, the CLI and hosted voice through the generated catalog (ADR 0004). An agent with only the folder can read and write the files.
- **Extraction happens where a model already is.** The voice agent calls `remember` during the conversation. When local voice ends, the bridge gives the person's own agent one silent turn to remember what it missed (`POST /voice/wrap-up`). Hosted voice, which already runs on the person's OpenAI key, has `saveVoiceConversation` extract the remaining facts. Without a model the transcript is still saved.
- **Recall is small and explainable.** Word overlap, the idea in view, general facts and recency rank memories; the same fact said again refreshes the old file (overlap ≥ 0.8), and a changed fact replaces it (`replaces`), moving the old file to `.trash`. Both voices load what's remembered at the start of a conversation and when the idea changes.
- **Every agent is told.** The rule (recall first, remember lasting facts, keep Manifest facts in Manifest memory) is in the `manifest` skill, the `manifest-memory` skill, Gemini's `CONTEXT.md`, the `/mcp` server instructions that every MCP client receives (so an agent with a stale plugin still gets it), and both voice prompts. A tooling test fails if a channel loses it.
- **Seamless by default.** Nothing to save by hand. After voice, a card says "Remembered N things" with an undo for each; Account → Data & storage → Memory lists, edits and forgets them; "forget that" works by voice.

## Consequences

- Memories count toward the vault's 5,000-file limit (capped at 2,000 memories).
- Word-overlap recall misses paraphrases ("revenue" vs "pricing"). If that matters, add an index (SQLite FTS on the Mac, pgvector on the server) over the same files; the files stay the source.
- Agents can phrase facts differently; dedup is per idea and lexical, so near-duplicates in other words can remain until the person or an agent replaces them.
- Agents' own memories (Claude Code, Codex) still exist beside Manifest's; the rule steers Manifest facts here but can't stop an agent from also keeping its own copy.
