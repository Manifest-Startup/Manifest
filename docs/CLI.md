# Manifest CLI

`manifest` does everything you can do in Manifest from a terminal: every GraphQL query and mutation is a command, plus sign-in, the REST-only features and two escape hatches. Design and security: [ADR 0003](adr/0003-manifest-cli-browser-login.md).

## Install

```bash
pip install -e mcp_server          # from a checkout; installs `manifest` and `manifest-mcp`
manifest --help
eval "$(manifest completion zsh)"  # or: manifest completion bash
```

Python 3.11+ recommended (3.10 works). The only runtime dependency the CLI uses is `httpx`.

## Sign in

```bash
manifest login                                  # https://manifeststartup.com
manifest login --base-url http://localhost:8000 # a local backend
manifest whoami
manifest logout                                 # revokes this computer's session
```

`login` opens Manifest in your browser. Sign in with Open Media if needed (passkeys and MFA apply); if your browser's sign-in is more than 5 minutes old, Manifest sends you through Continue with Open Media once more to confirm it's you. Then click **Allow** on "Allow Manifest CLI on this computer?". The CLI receives a session labelled `Manifest CLI · <hostname>` that lasts 30 days (14 days without use) and appears under Account → Security → Active sessions, where you can revoke it. There is no refresh: run `manifest login` again when it expires. Guest workspaces can't use the CLI; sign in first (your guest ideas merge into the account).

The session is stored in `~/.config/manifest/cli.json` (mode 0600) with the base URL. `MANIFEST_CONFIG` moves that file; `MANIFEST_API_URL` and `MANIFEST_API_TOKEN` override it (CI, a second deployment). Every request sends `Authorization: Bearer <token>`.

Routes that need a recent sign-in (create, rotate or revoke API keys; DSAR rectify or erase) answer `401` with `X-Step-Up-Required`, and the CLI says so. Because approving the CLI always needs a fresh sign-in, which the new CLI session inherits, re-running `manifest login` restores step-up access: run it, then retry within 5 minutes. `manifest logout` clears `cli.json` only when the revoked token came from it; with `--token` or `MANIFEST_API_TOKEN` the saved login stays.

## Voice

```bash
pip install -e 'mcp_server[voice]'   # adds websockets + sounddevice
manifest voice                       # talk; the mic mutes while Manifest speaks
manifest voice --barge-in            # with headphones: interrupt it any time
manifest voice --text                # type instead (needs only websockets)
```

`manifest voice` joins the same live voice agent as the web app (`WS /api/voice-agent/live`, see [VOICE_AGENT_API.md](VOICE_AGENT_API.md)). Speech recognition, the model, Manifest's tools and speech run on the server with your own OpenAI key, so it can do everything these commands can; it asks for a spoken yes before anything destructive. The CLI only moves audio (16 kHz up, 24 kHz down) and prints the conversation and each action it takes.

### Voice in the app with no OpenAI key: `manifest bridge`

Set it up from nothing in one step (installs the CLI with uv and starts the bridge at login):

```bash
curl -fsSL https://manifeststartup.com/voice.sh | sh
```

```bash
manifest bridge                            # Claude Code (or Codex if that's what's installed) answers voice
manifest bridge --agent codex              # or Codex, or any command (as for `voice --agent`)
manifest bridge --agent claude --continue  # pick up your newest Claude Code session here
manifest bridge --model default            # keep the agent's own model (voice uses Claude's haiku by default, for speed)
manifest bridge --install                  # macOS: start it at login and keep it running (--uninstall undoes)
```

The browser listens and speaks, so the first word comes about 2–3 s after you stop talking. You can talk over it: it stops speaking, interrupts the agent, and takes your new question. Tapping the orb or pressing Space also stops it. See [ADR 0017](adr/0017-voice-feels-instant.md).

**Natural voice, no key (Apple silicon, about 16 GB of RAM or more):** with `pip install 'manifest-mcp[local-voice]'` the bridge also runs a Pipecat voice on `ws://127.0.0.1:47822`: Silero VAD and smart-turn, Whisper large-v3-turbo (MLX, quantized), your agent as the brain, and Kokoro's neural voice (`--voice af_heart`). On smaller Macs it stays off, because the models swap and answers would take seconds; `--voice af_heart` forces it on. The first start downloads the models (about 1 GB).

Keep it running and use voice in the web app or the installed app. With no OpenAI key on the account (or in a vault without signing in), the app's voice button uses the browser's own speech recognition and voice, and each turn goes to your agent through this small server on `http://127.0.0.1:47821`. It answers only Manifest's own pages (`--origin` adds a self-hosted one), so other websites cannot drive your agent; Chrome may ask once to let Manifest reach the local network. No sign-in or key is needed. The note's dictation orb needs neither the bridge nor a key: without a key it uses the browser's recognition (Chrome sends the audio to Google's speech service; Safari uses Apple's).

### Where your vault lives: `manifest vault-folder`

```bash
manifest vault-folder                      # where the vault is on this computer
manifest vault-folder icloud               # move it to iCloud Drive (or documents, home, or a full path)
```

Moving keeps every file (it refuses a place that isn't empty), restarts background sync on the new folder, gives it the Manifest folder icon and saves the choice in `~/.config/manifest/vault.json` for the plugin, the app and voice. It runs the vault script from the Manifest plugin (`manifest_vault.py move`). The running bridge exposes the same thing to Settings → Storage (`GET`/`POST /vault/folder`), and Claude Code may run this one command during voice without asking, so "move my vault to iCloud Drive" works out loud.

### Your GitHub: `manifest github`

```bash
manifest github connect                    # links the GitHub login on this computer (gh, or the GitHub plugin's token)
manifest github                            # connected as whom, with which scopes
manifest github-repos --query api          # then every github-* command works
manifest github-issues --repo you/app --state all
manifest github-create-pull-request --repo you/app --title "Add login" --head feature/login
manifest github-merge-pull-request --repo you/app --number 12        # asks first (--yes to skip)
manifest github-workflow-runs --repo you/app                         # is CI green?
manifest github-api --path /notifications                            # anything else (GET)
manifest commands --search github                                    # all 33
```

It's one connection: checked with GitHub, stored encrypted in your account, and shared by the app (Settings → Integrations → GitHub), the agent plugin (`manifest-github` skill) and voice. Connecting or disconnecting anywhere shows everywhere. `--token-stdin` reads a token from a pipe for scripts; `manifest github disconnect` forgets it.

### Your own agent, out loud

```bash
manifest voice --agent claude              # Claude Code answers; Manifest listens and speaks
manifest voice --agent claude --continue   # continue the newest Claude Code session in this folder (also VS Code's)
manifest voice --agent claude --resume <session-id>
manifest voice --agent codex               # OpenAI Codex CLI
manifest voice --agent "./my-agent.sh"     # any command: the turn on stdin, its output is spoken
manifest voice --agent claude --agent-arg=--permission-mode=acceptEdits   # pass flags through
```

With `--agent`, the server runs relay mode: it transcribes and speaks with your OpenAI key, and the agent you already use answers on this computer with its own tools, permissions and history. Claude Code runs as one long-lived process for the whole conversation (it starts while you speak, so its MCP servers and hooks start once), is read-only by default (Manifest plugin tools, Read/Grep/Glob, web search) and is told its replies are spoken. Your Claude Code Stop hooks still run after each answer; a slow one delays the *next* turn, not the answer.

## GraphQL commands

Each query and mutation is a kebab-case command; arguments are flags.

```bash
manifest commands --search idea          # list (add --json for scripts)
manifest ideas                           # readable table
manifest ideas --json                    # raw JSON
manifest create-idea --title "Lawn robots" --description "Autonomous mowing"
manifest idea --idea-id <id> --select "ideaId title isPublished"
manifest update-account --first-name Ada --bio "Founder"   # input-object fields as flags
manifest update-account --input @account.json              # or the whole input: JSON, @file or - (stdin)
manifest delete-idea --idea-id <id> --yes                  # destructive: prompts unless --yes
manifest create-idea --title x --print-query               # show the GraphQL document instead
```

- `--help` on any command shows its description, return type, default fields and flags.
- Default output selects scalar fields two levels deep; `--select` overrides it.
- Destructive mutations (delete, remove, revoke, investments and contributions, disconnect, restore, publish, role changes, account deletion) ask for confirmation, and refuse to run without `--yes` when stdin is not a terminal.
- `--variables` passes all variables as JSON (flags win).
- Some mutations generate documents with your own OpenAI key (Account → AI settings) and can take a while.

## REST commands

| Command | Endpoint |
| --- | --- |
| `manifest keys clients \| create-client \| delete-client <id>` | `/api/keys/clients` |
| `manifest keys create \| rotate \| revoke <key_id>` | `/api/keys/keys` |
| `manifest keys tiers \| usage` | `/api/keys/tiers`, `/api/keys/usage` |
| `manifest privacy consent \| set-consent \| withdraw-consent` | `/api/privacy/consent` |
| `manifest dsar access \| export \| rectify \| object \| erase \| erase-certificate \| retention-exceptions` | `/api/dsar/*` |
| `manifest upload-profile-picture <file>` | `POST /api/account/profile-picture` |
| `manifest github-bootstrap --idea-id … --repo-name …` | `POST /api/integrations/github/bootstrap` |
| `manifest voice-capabilities` | `GET /api/voice-agent/capabilities` |
| `manifest trust-center` | `GET /api/trust-center` |

Not wrapped on purpose: voice audio streaming and realtime sessions, internal and admin loops, SSO/SCIM, webhooks, and the API-key `/api/v1` routes (use `manifest api` with `MANIFEST_API_TOKEN=<key>`, or the MCP server).

## Escape hatches

```bash
manifest graphql '{ mySessions { sessionId kind userAgent current } }'
manifest graphql @query.graphql --variables '{"ideaId": "…"}'
manifest api GET /api/keys/usage
manifest api POST /api/keys/clients --data '{"name": "ci"}'
```

## Keeping the CLI complete (maintainers)

The commands come from `mcp_server/src/manifest_cli/catalog.json`, generated from the Strawberry schema (production disables introspection, so the CLI ships the catalog). After **any** GraphQL schema change:

```bash
.venv/bin/python scripts/generate_cli_catalog.py          # regenerate and commit catalog.json
.venv/bin/python scripts/generate_cli_catalog.py --check  # what scripts/check.py (area `cli`) runs
```

`python3 scripts/check.py` and `tests/tooling/test_cli_catalog.py` fail until the catalog matches. A new field name that collides with a built-in or REST command (`login`, `keys`, …) fails generation. Add a resolver docstring or `strawberry.field(description=…)` to improve a command's `--help`; new REST-only user features go in `manifest_cli/rest.py`.
