# MCP server — agent guide (child of [`../AGENTS.md`](../AGENTS.md))

Python package `manifest_mcp` (`src/manifest_mcp/server.py` = FastMCP tools, `client.py` = typed HTTP client for a running Manifest deployment). It mirrors public backend contracts, so it must change when the backend API it calls changes. `README.md` lists the tools.

- `src/manifest_cli/` is the `manifest` CLI (docs/CLI.md). Its `catalog.json` is generated: run `../.venv/bin/python ../scripts/generate_cli_catalog.py` after any GraphQL schema change, never edit it by hand. Then run `../scripts/generate_agent_tools.py`: the hosted `/mcp` tools and the agent plugin (`../agent-plugin/`, ADR 0004) are generated from the same catalog and `rest.py`.
- Every tool calls the backend through `client.py`; never import `backend/app` code here.
- Keep tool names and input schemas stable; they are a public contract for external agents.
- Install for local work: `uv pip install --python ../.venv/bin/python -e .`

```bash
pytest tests -q
python3 ../scripts/check.py --only python mcp
```
