# 0023. One bridge, several agents, honest setup

- Status: accepted
- Date: 2026-11-23
- Issue: #132

## Context

A person with Codex installed set up voice with `manifest bridge --install --agent codex`. The login item ran in their home folder, and `codex exec` refuses to run outside a Git repository ("Not inside a trusted directory and --skip-git-repo-check was not specified"). The bridge hid this on fresh turns by passing `--skip-git-repo-check`, but resumed turns (`codex exec resume`) don't get that flag, so voice broke on the second question. Meanwhile the log said "Manifest can now talk to Codex". The login item also rebuilt its options by hand, so foreground and installed runs could differ.

People also use more than one agent. Voice should answer with the one they are working with now, and switching should keep the conversation.

## Decision

1. **One saved source of truth.** `~/.config/manifest/bridge.json` (schema 2, mode 0600, atomic writes) holds `default` (`active` or an agent), one profile per agent (folder, model, continue or resume, approved arguments), and the port, origins and voice. The login item runs `manifest bridge --config <file>`. A plain `manifest bridge` runs the same file. An older login item's options are read once and kept as they are (same agent, same rights).
2. **Never bypass Codex's trust check.** `--skip-git-repo-check` is removed from every command and refused in saved settings. Codex runs with its project as its working directory: the folder the person chooses, by default the Git root of their newest Codex session. Manifest never edits Codex's config. Measured with codex-cli 0.172: a `trust_level = "trusted"` entry outside Git is not enough for `exec`, so a Git repository is the test.
3. **Ready means able to answer.** Readiness checks (agent installed, folder exists, Codex project, signed in) have stable codes (`agent_missing`, `workdir_missing`, `trust_required`, `auth_needed`, `port_in_use`, `launch_failed`, …), a message and a fix. `/health` reports `ready`, `problems` and `agents`. `--install` waits for the installed bridge's own `/health` before it says "Ready". `--doctor --probe` sends a real test turn through the same agent command. A known launch error is translated into the next step.
4. **Several agents, the active one by default.** Every installed agent gets a profile. With `active`, the bridge answers with the agent whose newest session file is most recent. Only file times and the session's folder are read, never conversation content. It picks again when a new conversation starts (after 2 minutes idle), and skips agents that can't answer. An agent chosen by name is never silently replaced.
5. **Seamless switching.** "Switch to Codex" said aloud, `POST /agent` from the app, or `manifest bridge --use codex` switches at once and is saved. The new agent's next turn carries the last 12 exchanges of this voice conversation, once. Each agent keeps its own live session, so switching back resumes it. Long-term memory shared by all agents is the vault memory of ADR 0021.

## Follow-up: fast, interruptible, the same for every agent (2026-11-23)

The person's live test found Codex voice slow (6–8 s a turn), unable to use Manifest ("the Manifest feedback tool isn't connected"), hard to interrupt, and curt.

- **Codex stays warm.** It runs as one `codex app-server` (JSON-RPC over stdio, the protocol Codex's IDE extension uses) for the whole call. Words stream sentence by sentence, and talking over it sends `turn/interrupt` and stops speaking at once. A throwaway turn while the call connects starts its MCP servers early. Measured on the real stack: first words 2.5 s, follow-ups 1.4–2.1 s, and an interrupt took 0.06 s, against 6–8 s for `codex exec` per turn. `--continue` still uses `exec resume`.
- **Every agent gets Manifest's tools from the CLI sign-in.** The hosted `/mcp` accepts the CLI token. The bridge puts it only in the agent's environment (`MANIFEST_MCP_TOKEN`), never in arguments or logs. Codex points its `manifest` MCP server at it. When neither the CLI nor Codex is signed in, `/health` and the panel show a `manifest_not_connected` note with the fix.
- **"The agent you used last" ignores voice's own sessions:** Codex `originator: manifest-voice` or `source: exec`, and Claude Code `entrypoint: sdk-cli`.
- **Switching warms the new agent at once.** On a Mac under 16 GB it also stops the previous agent's process and keeps its session, so the two never share memory.

## Consequences

- Codex users must pick a Git project for voice. Setup asks for one in a terminal, or explains `--workdir`.
- The session-recency heuristic may pick the agent the bridge itself just used. That is intended: the agent you last talked to stays the default.
- Diagnostics stay local. `/health` names only the folder's last part, and nothing is sent anywhere.
