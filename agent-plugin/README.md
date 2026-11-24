<p align="center"><img src="assets/icon.png" width="96" height="96" alt="Manifest"></p>

<h1 align="center">Manifest for AI agents</h1>

<p align="center">From a rough idea to an investable plan, in Claude, ChatGPT, Codex, VS Code, Cursor, Gemini and Antigravity.<br>Everything you can do in Manifest, your agent can do too, and it asks before anything destructive.</p>

---

## What you can ask

> **"I have an idea for cold storage that runs on solar. Put it in Manifest."** It checks what already exists, proposes a title and description, and runs the qualification interview with you.
>
> **"Make the pitch deck and PRD for it."** Your agent writes them itself, following Manifest's own document guides, and saves them to the idea. No OpenAI key needed; if you've added one, Manifest can generate them too.
>
> **"Save this thought about pricing."** Saved right away as a note in your local vault, linked to the idea, so Obsidian's graph shows how your ideas, documents, skills and notes connect.
>
> **"Who messaged me about my ideas?"** Founder messages through your linked Open Media account, drafted replies sent only after you say yes.
>
> **"Log 20 hours of sweat equity on Solar Cold Chain at $60 an hour."** The numbers are read back to you before anything is recorded.
>
> **"Invite dev@example.com as an editor, and snapshot the idea first."**
>
> **"Which apps are signed in to my account?"** Sessions, connected agents, privacy choices and data requests.

Prefer talking? The **Voice** button in the app and `manifest voice` in a terminal run a live voice agent with these same tools and the same confirm-before-destructive rule ([how it works](../docs/VOICE_AGENT_API.md)).

## Install

| Where | How |
|---|---|
| **Claude Code** | `claude plugin marketplace add Manifest-Startup/Manifest` then `claude plugin install manifest@manifest` |
| **Codex** | `codex plugin marketplace add Manifest-Startup/Manifest` then `codex plugin add manifest@manifest` |
| **Claude, ChatGPT (connectors)** | Add a custom connector with `https://manifeststartup.com/mcp` and sign in |
| **VS Code** | Command palette → *Chat: Install Plugin from Source* → `Manifest-Startup/Manifest`, or [add the MCP server](vscode:mcp/install?%7B%22name%22%3A%22manifest%22%2C%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fmanifeststartup.com%2Fmcp%22%7D) |
| **Cursor** | Plugins marketplace → *Manifest*, or install from `Manifest-Startup/Manifest`, or [add the MCP server](cursor://anysphere.cursor-deeplink/mcp/install?name=manifest&config=eyJ1cmwiOiJodHRwczovL21hbmlmZXN0c3RhcnR1cC5jb20vbWNwIn0=) |
| **Antigravity** | `agy plugin install ./agent-plugin` from a clone of the repository |
| **Gemini CLI** | `gemini extensions install https://github.com/Manifest-Startup/Manifest` |
| **OpenCode, Amp, Goose, Windsurf** | Add a remote MCP server with the URL `https://manifeststartup.com/mcp` in its MCP settings |
| **Any MCP client** | Streamable HTTP at `https://manifeststartup.com/mcp`; OAuth is discovered automatically |
| **Skills only** | `npx skills add Manifest-Startup/Manifest` |

Then try **`/manifest:new-idea`**, **`/manifest:note`**, **`/manifest:write-docs`**, **`/manifest:vault`**, **`/manifest:ideas`**, **`/manifest:plan`**, **`/manifest:pitch`**, **`/manifest:messages`**, **`/manifest:portfolio`** or **`/manifest:account`** in Claude Code, or just ask.

## Your vault and knowledge graph

With a local agent (Claude Code, Codex, Cursor, Gemini CLI…), Manifest keeps an Obsidian-style vault on your computer: `~/Manifest Vault` until you move it (`manifest_vault.py move icloud`, Settings → Storage in the app, or just ask voice), or inside your own Obsidian vault. On a Mac the folder wears the Manifest folder icon. Ideas, documents, interviews and skills are Markdown files with frontmatter and `[[wiki-links]]`; notes you dictate land in `Notes/`, linked to their ideas. Open it in Obsidian and switch on Graph view. It syncs with your Manifest account like iCloud Drive or OneDrive: run `manifest_vault.py login` and `manifest_vault.py install` once per computer, and your notes and writing follow you, edited offline or not. The plugin's `manifest_vault.py` never deletes anything (deletions from another computer go to `.trash/`, edits in two places keep both copies) and keeps whatever you write around the generated block.

## Signing in

The first time your agent uses Manifest, a browser page opens: sign in with Open Media (passkeys work) and click **Allow**. That's it. Your agent never sees a password or token, and it appears under **Account → Security → Active sessions** as "AI agent · <app>", where you can disconnect it at any time. Connecting an agent needs a sign-in from the last five minutes, the same rule as the Manifest CLI.

Scripts can still use an API key (`Authorization: Bearer manifest_sk_…`), which unlocks the small REST toolset only.

## What's inside

- **1 MCP server**, `manifest` at `https://manifeststartup.com/mcp`, with **191 tools**: every GraphQL query and mutation and every account REST feature, generated from the schema (see [TOOLS.md](TOOLS.md)). The few operations that stay in the app are listed there with the reason.
- **12 skills**: `manifest` (start here), `manifest-ideas`, `manifest-documents`, `manifest-customers`, `manifest-goals`, `manifest-vault`, `manifest-github`, `manifest-network`, `manifest-investing`, `manifest-team`, `manifest-account` and `manifest-admin`.
- **13 slash commands**: `new-idea`, `note`, `ideas`, `plan`, `customers`, `write-docs`, `vault`, `github`, `feedback`, `pitch`, `messages`, `portfolio` and `account`.

Pair it with the [Open Media plugin](https://github.com/Manifest-Startup/open-media) for the rest of your Open Media inbox and feed; Manifest's messages and pitch shorts run on the same account.

## Safety, by design

- Destructive tools (delete, publish, invest, revoke, erase…) refuse to run until the agent has shown you what will happen and called again with `confirm: true`. Every tool carries MCP read-only and destructive hints, so hosts can ask you too.
- The agent acts as you, so Manifest's own permission checks apply to every call.
- Credentials are never selected into the agent's context: no integration tokens, no OpenAI key, no session secrets.
- Idea text, documents, messages and comments are treated as data, never instructions.
- Generated documents are drafts for you to review, not legal, financial or investment advice.

## For marketplaces and maintainers

"Everything is a plugin": the GraphQL schema is the source, and everything else is generated from it or checked against it (ADR 0004).

```
backend GraphQL schema ──generate_cli_catalog.py──▶ manifest_cli/catalog.json ──▶ manifest CLI
                                         └──generate_agent_tools.py──▶ mcp-tools.generated.json ──▶ /mcp tools
                                                                     └──▶ agent-plugin/TOOLS.md
skills/*/SKILL.md ◀── tests/tooling/test_agent_plugin.py fails if any tool is untaught or unknown
```

| File | Read by |
|---|---|
| `.claude-plugin/plugin.json`, `.mcp.json`, `commands/` | Claude Code, Claude Cowork, VS Code agent plugins, GitHub Copilot CLI |
| `.codex-plugin/plugin.json` | Codex |
| `plugin.json` + `mcp.json` | Agent Plugins standard (agent-plugins.org), Kiro powers |
| `.cursor-plugin/plugin.json` + `.cursor-plugin/mcp.json`, `../.cursor-plugin/marketplace.json` | Cursor (cursor.com/docs/reference/plugins) |
| `../glama.json` | Glama |
| `.antigravity-plugin/plugin.json` + `mcp_config.json` | Antigravity |
| `registry/manifest.server.json` | Official MCP Registry (`com.manifeststartup/manifest`) |
| `skills/` | every host above, and `npx skills` |
| `../gemini-extension.json` + `CONTEXT.md` | Gemini CLI |
| `../.claude-plugin/marketplace.json`, `../.agents/plugins/marketplace.json` | Claude Code and Codex marketplaces |

After a schema or `rest.py` change: `python3 scripts/generate_cli_catalog.py && python3 scripts/generate_agent_tools.py`. `python3 scripts/check.py` (area `plugin`) fails until the tools are regenerated and every new tool is in a skill. Keep the name, version and server URL equal in every manifest (the same test checks).
