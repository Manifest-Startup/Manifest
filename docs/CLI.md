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

`login` opens Manifest in your browser. Sign in with Open Media if needed (passkeys and MFA apply), then click **Allow** on "Allow Manifest CLI on this computer?". The CLI receives a session labelled `Manifest CLI · <hostname>` that lasts 30 days (14 days without use) and appears under Account → Security → Active sessions, where you can revoke it. There is no refresh: run `manifest login` again when it expires. Guest workspaces can't use the CLI; sign in first (your guest ideas merge into the account).

The session is stored in `~/.config/manifest/cli.json` (mode 0600) with the base URL. `MANIFEST_CONFIG` moves that file; `MANIFEST_API_URL` and `MANIFEST_API_TOKEN` override it (CI, a second deployment). Every request sends `Authorization: Bearer <token>`.

Routes that need a recent sign-in (create, rotate or revoke API keys; DSAR rectify or erase) answer `401` with `X-Step-Up-Required`: run `manifest login` again, then retry within 5 minutes.

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
