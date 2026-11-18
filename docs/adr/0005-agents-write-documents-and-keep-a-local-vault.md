# 0005. The person's agent writes documents, and keeps a local vault

- Status: Accepted (2026-11-18). Builds on [0004](0004-agents-get-everything-through-one-plugin.md).
- Skills: `agent-plugin/skills/manifest-documents`, `agent-plugin/skills/manifest-vault`

## Context

Manifest exists to get a founder from idea to execution. Its document generators run on the person's own OpenAI key (bring your own key); without a key they silently fall back to generic templates, so a new founder's first canvas, deck and PRD said nothing about their idea. Yet anyone using Manifest through an agent is already talking to a capable model. Founders also think out loud: what they say about an idea should be kept, linked and findable on their own computer, not only in a web app.

## Decision

- **The agent is a writer.** `documentGuide(documentType)` returns Manifest's own prompt (`app/prompts/*.mcp.json`) for the canvas, pitch deck, PRD and provisional patent, plus a similar-ideas guide, so agent-written documents keep Manifest's structure. `saveIdeaDocument(ideaId, documentType, content)` stores a written document exactly where generated ones go (`ideas.<column>`, plus `pitch_decks` / `product_requirements_documents`), for owners and editors. `saveBmcSection` stores one canvas section as a user edit. The documents skill picks the writer: Manifest when `aiKeyStatus` is configured, otherwise the agent, and offers to rewrite template documents.
- **A local, Obsidian-style vault.** `vaultExport(sinceUpdatedAt)` (`app/services/ideas/vault.py`) renders the person's own ideas, documents, canvas sections, interviews and skills as Markdown files under `Manifest/` with YAML frontmatter, tags and `[[wiki-links]]` (idea ↔ documents ↔ skills ↔ related ideas by shared skills and vocabulary ↔ interviews), plus `Home.md`. The plugin's offline `manifest_vault.py` writes them into `$MANIFEST_VAULT` or `~/Manifest Vault`, replacing only the frontmatter and the marked generated block, never deleting, never touching files it didn't write, and confined to the vault folder. `manifest_vault.py note` saves the person's own notes in `Notes/`, linked to ideas, as they talk. Obsidian's Graph view is the knowledge graph.
- Everything stays a plugin: the new operations are GraphQL fields, so the CLI and the MCP tools are regenerated from the schema; the skills and commands name them, and `check.py` area `plugin` keeps it all consistent.

## Consequences

- No key is needed to get real documents; the founder's own agent does the work and the founder's key, if any, still powers Manifest-side generation.
- Agent-written documents carry no "AI-written" marker in the database; the skill snapshots the previous version with `createIdeaVersion` before overwriting.
- The vault needs a host with a local shell (Claude Code, Codex, Cursor, Gemini CLI); web connectors can create documents but not local files.
- Notes are local only; syncing notes back into Manifest is a possible next step. Superseded by [0007](0007-the-vault-syncs-with-your-account.md): the vault now syncs with the account.
