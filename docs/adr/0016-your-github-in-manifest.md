# 0016. Your own GitHub, connected once and controlled from everywhere

- Status: Accepted (2026-11-20).
- Code: `backend/app/services/integrations/github_account.py` (connect, encrypted token), `github_api.py` (every operation), `backend/app/graphql/resolvers/github.py` (`github*` fields), `frontend/src/features/account/components/GitHubSection.tsx`, `manifest github` in `mcp_server/src/manifest_cli/main.py`, `agent-plugin/skills/manifest-github/SKILL.md`

## Context

GitHub showed up as an integration, but on production it could not really be connected. Sign in with GitHub had no OAuth app configured, so "Connect" saved a GitHub row with no token. Creating a repository from an idea then failed. It also read only the plaintext token column, so an encrypted token would have broken it. The one GitHub action the person had was "create a repo". Founders want their agent and their voice to work in their code: issues, pull requests, CI and releases.

## Decision

- **One connection, one action.** GitHub is a single "Connect GitHub" card at the top of Settings → Integrations, not in the catalog grid. Its status pill reads "GitHub @login". The button uses Sign in with GitHub (OAuth app, scopes `repo workflow read:org read:user user:email delete_repo`) when `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` are set. Otherwise its next step asks for a token, opening GitHub's token page with those scopes filled in. It's never two options side by side. `manifest github connect` writes the same connection. It links the GitHub login already on the computer in one step: the GitHub CLI (`gh auth token`), or the token the GitHub plugin / MCP server reads (`GITHUB_PERSONAL_ACCESS_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`). That way nobody connects twice and no token passes through a chat or a voice. Every token is verified with `GET /user` and always encrypted with the person's tenant key, like their OpenAI key. Only the login, name and scopes stay in clear (`metadata`). The one `integrations` row (`github`) powers the app, repos from ideas, the CLI, the hosted MCP and plugin, and both voices, so connecting or disconnecting anywhere shows everywhere. GitHub is never recorded without a token.
- **Everything is a GraphQL field**, so the CLI, the hosted `/mcp` tools, the agent plugin and both voices get it from the generator with no hand-written copies (ADR 0004, 0013). The fields cover: account (`githubAccount`, `connectGithub`, `disconnectGithub`), repositories, issues and comments, pull requests (review, merge), branches, commits, files (read, commit, delete), Actions (list, run, re-run, cancel), releases, and `githubApi` / `githubApiRequest` for any other REST call on api.github.com (paths are checked so they can't leave that host).
- **Ask before harm.** Deleting (repos, branches, files), disconnecting, merging, repository settings and raw write calls are destructive in the catalog. The CLI asks, and agents and voice must show the change and get `confirm: true`.
- **Errors say what to do**, for example: reconnect, the token lacks a scope, the rate limit is used up, or it doesn't exist or the token can't see it.

## Consequences

- Production needs no new secret: tokens work today. Sign in with GitHub appears once the owner creates an OAuth app (callback `https://manifeststartup.com/auth/github/callback`) and sets the two variables on Render.
- Calls are made live with the person's token. Nothing from their repositories is stored in Manifest.
- A fine-grained token carries no scopes header, so the app can't warn about missing access ahead of time. GitHub's 403 message explains it at use instead.
