"""The Manifest agent plugin: one folder, every marketplace, full parity (ADR 0004).

- Every manifest names the same plugin, version and MCP server.
- Every generated agent tool is taught by at least one skill, and no skill or command names
  a tool that doesn't exist, so a new GraphQL field can't ship without agents knowing it.
- Every GraphQL operation and REST command is either a tool or excluded with a reason.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "agent-plugin"
TOOLS = json.loads((ROOT / "deploy/cloudflare/src/mcp-tools.generated.json").read_text())
CATALOG = json.loads((ROOT / "mcp_server/src/manifest_cli/catalog.json").read_text())
MCP_URL = "https://manifeststartup.com/mcp"
NAMES = {t["name"] for t in TOOLS["tools"]}


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def skills() -> dict[str, str]:
    return {p.parent.name: p.read_text() for p in sorted((PLUGIN / "skills").glob("*/SKILL.md"))}


def test_every_manifest_agrees():
    standard = load("agent-plugin/plugin.json")
    manifests = [
        standard,
        load("agent-plugin/.claude-plugin/plugin.json"),
        load("agent-plugin/.codex-plugin/plugin.json"),
        load("agent-plugin/.antigravity-plugin/plugin.json"),
        load("agent-plugin/.cursor-plugin/plugin.json"),
        load("gemini-extension.json"),
    ]
    assert {m["name"] for m in manifests} == {"manifest"}
    assert {m["version"] for m in manifests} == {standard["version"]}
    assert load("agent-plugin/registry/manifest.server.json")["version"] == standard["version"]
    servers = [
        load("agent-plugin/.mcp.json")["mcpServers"]["manifest"]["url"],
        load("agent-plugin/mcp.json")["mcpServers"]["manifest"]["url"],
        load("agent-plugin/mcp_config.json")["mcpServers"]["manifest"]["serverUrl"],
        load("agent-plugin/.cursor-plugin/mcp.json")["mcpServers"]["manifest"]["url"],
        load("gemini-extension.json")["mcpServers"]["manifest"]["httpUrl"],
        load("agent-plugin/registry/manifest.server.json")["remotes"][0]["url"],
    ]
    assert set(servers) == {MCP_URL}
    for marketplace in (
        load(".claude-plugin/marketplace.json"),
        load(".agents/plugins/marketplace.json"),
    ):
        (entry,) = marketplace["plugins"]
        source = entry["source"] if isinstance(entry["source"], str) else entry["source"]["path"]
        assert entry["name"] == "manifest" and source == "./agent-plugin"
    (cursor,) = load(".cursor-plugin/marketplace.json")["plugins"]
    assert cursor["name"] == "manifest" and cursor["source"] == "agent-plugin"
    assert (ROOT / load("gemini-extension.json")["contextFileName"]).is_file()


def test_no_manifest_holds_a_secret():
    text = (
        " ".join(p.read_text() for p in PLUGIN.rglob("*.json"))
        + (ROOT / "gemini-extension.json").read_text()
    )
    assert "manifest_sk_" not in text and "Authorization" not in text and "${" not in text


def test_skills_are_valid_agent_skills():
    found = skills()
    assert "manifest" in found
    for name, text in found.items():
        front = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", text)
        assert front, name
        assert front.group(1) == name
        assert 20 < len(front.group(2)) <= 1024


def test_every_tool_is_taught_by_a_skill():
    mentioned = set()
    for text in skills().values():
        mentioned |= set(re.findall(r"`([a-z][a-z0-9_]+)`", text))
    missing = sorted(NAMES - mentioned)
    assert not missing, f"tools no skill explains (add them to agent-plugin/skills): {missing}"


def test_skills_and_commands_only_name_real_tools():
    texts = list(skills().values()) + [p.read_text() for p in (PLUGIN / "commands").glob("*.md")]
    words = set()
    for text in texts:
        words |= {w for w in re.findall(r"`([a-z][a-z0-9_]+)`", text) if "_" in w}
    allowed = {
        "manifest_sk_",
        "document_types",
        "business_model_canvas",
        "pitch_deck",
        "prd",
        "patent",
    }
    unknown = sorted(w for w in words - NAMES - allowed if not w.startswith("manifest"))
    assert not unknown, f"skills or commands name tools that don't exist: {unknown}"


def test_every_operation_is_a_tool_or_excluded_with_a_reason():
    sys.path.insert(0, str(ROOT / "mcp_server" / "src"))
    from manifest_cli.rest import REST_COMMANDS

    def snake(name: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().replace("-", "_")

    excluded = TOOLS["excluded"]
    assert all(len(reason) > 20 for reason in excluded.values())
    for op in CATALOG["operations"]:
        assert snake(op["name"]) in NAMES or op["name"] in excluded, op["name"]
    for cmd in REST_COMMANDS:
        name = snake(f"{cmd.group}_{cmd.name}" if cmd.name else cmd.group)
        assert name in NAMES or f"rest:{cmd.command.replace(' ', '-')}" in excluded, cmd.command


def test_tools_table_is_published_with_the_plugin():
    table = (PLUGIN / "TOOLS.md").read_text()
    assert f"**{len(NAMES)} tools**" in table
    readme = (PLUGIN / "README.md").read_text()
    assert f"{len(NAMES)} tools" in readme, "update the tool count in agent-plugin/README.md"
    assert f"{len(skills())} skills" in readme
    assert f"{len(list((PLUGIN / 'commands').glob('*.md')))} slash commands" in readme


def test_every_generated_document_is_valid_against_the_schema():
    import importlib.util

    import pytest

    pytest.importorskip("strawberry", reason="needs the backend dependencies (.venv)")
    from graphql import parse, validate

    spec = importlib.util.spec_from_file_location(
        "gen_cli", ROOT / "scripts" / "generate_cli_catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = module._load_schema()._schema
    failures = {}
    for tool in TOOLS["tools"]:
        if tool["_call"]["via"] != "graphql":
            continue
        errors = validate(schema, parse(tool["_call"]["document"]))
        if errors:
            failures[tool["name"]] = [e.message for e in errors]
    assert not failures, failures


def test_arguments_with_defaults_can_be_left_out():
    """Leaving out `offset` or `hourlyRate` must use the server default, not fail as missing."""
    by_name = {op["name"]: op for op in CATALOG["operations"]}
    for tool in TOOLS["tools"]:
        call = tool["_call"]
        if call["via"] != "graphql":
            continue
        for arg in by_name[call["field"]]["args"]:
            if arg.get("default") is not None and not arg["required"]:
                assert (
                    f"${arg['name']}: {arg['type'].removesuffix('!')}"
                    in call["document"].split("{")[0]
                ), (
                    tool["name"],
                    arg["name"],
                )
