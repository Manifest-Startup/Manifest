# Contributing to Manifest

Thanks for helping. Manifest turns a rough startup idea into a business model canvas, research, documents and a pitch. Bug fixes, docs, tests and features are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the approach.
- Read [`AGENTS.md`](AGENTS.md). It is the map of the repository and links to a short guide for each part (`backend/`, `frontend/`, `deploy/cloudflare/`, `mcp_server/`).
- Security problems go to `security@manifeststartup.com` or a private GitHub advisory, never a public issue. See [`SECURITY.md`](SECURITY.md).

## Set up

```bash
git clone https://github.com/Manifest-Startup/Manifest.git && cd Manifest
uv venv .venv && uv pip install --python .venv/bin/python -r backend/requirements.txt -e mcp_server -e .
cd frontend && npm ci && cd ..
cp .env.example .env   # fill in what you need; the backend runs with an in-memory database if DATABASE_URL is unset
```

AI features use your own OpenAI API key: add it in the running app under Account → AI settings, or set `OPENAI_API_KEY` in `.env` as a local fallback. Details are in [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

## Find your way around

```bash
python3 scripts/codegraph/query.py find <name>      # where a function, component or file is defined
python3 scripts/codegraph/query.py impact <file>    # everything that depends on a file, including tests
python3 scripts/codegraph/query.py graphql <field>  # which resolver handles a GraphQL field
```

## Check your change

There is no CI test gate: the local check is the gate.

```bash
python3 scripts/check.py           # checks only the areas you changed
python3 scripts/check.py --all     # everything, about 70 seconds
python3 scripts/check.py --install-hook   # run it before every git push
```

It runs ruff (lint and format), the backend pytest suite, Jest related tests with `tsc` and ESLint, the edge Worker tests, the MCP server tests and the tooling tests. All suites are green on `main`, so any failure is real.

## Pull requests

- Keep each pull request to one change, with tests in proportion to the risk.
- Use Conventional Commit subjects (`feat:`, `fix:`, `docs:`, `refactor:`, `test:` …). Merges to `main` cut a SemVer release from these prefixes.
- Update the docs when behaviour or a public contract (GraphQL, REST, MCP tools) changes.
- Never commit credentials, customer data, `.env` files, generated PDFs, coverage or build output.
- Say in the description what you ran to check the change.

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
