#!/usr/bin/env python3
"""Generate the Manifest agent tools (MCP) from the same sources as the CLI (ADR 0004).

Everything is a plugin: the GraphQL catalog (``mcp_server/src/manifest_cli/catalog.json``,
itself generated from the schema) and the REST list (``manifest_cli/rest.py``) are the only
sources. This script turns them into MCP tool definitions that the edge Worker serves at
``/mcp`` (``deploy/cloudflare/src/mcp-tools.generated.json``) and writes the tool table in
``agent-plugin/TOOLS.md``. Nothing about a tool is written by hand except the short
``EXCLUDED`` list below, and each exclusion carries the reason an agent can give.

    python3 scripts/generate_agent_tools.py          # write
    python3 scripts/generate_agent_tools.py --check  # fail if the committed files drift

Run it after ``generate_cli_catalog.py`` whenever the schema or ``rest.py`` changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "mcp_server" / "src" / "manifest_cli" / "catalog.json"
OUT = ROOT / "deploy" / "cloudflare" / "src" / "mcp-tools.generated.json"
# The live voice agent runs the same tools (backend/app/services/voice/live/tools.py).
VOICE_OUT = ROOT / "backend" / "app" / "services" / "voice" / "live" / "tools.generated.json"
TABLE = ROOT / "agent-plugin" / "TOOLS.md"

sys.path.insert(0, str(ROOT / "mcp_server" / "src"))
from manifest_cli.rest import REST_COMMANDS  # noqa: E402

# Operations people can't or shouldn't do through an agent, with the reason shown to agents.
EXCLUDED: dict[str, str] = {
    "startGuestSession": "Creates a throwaway guest workspace; agents always act as the signed-in person.",
    "logoutUser": "Would end the agent's own session. Disconnect an agent under Account → Security → Active sessions, or use revoke_account_session.",
    "openMediaRealtimeToken": "Returns a live Open Media credential for the web app's realtime socket; agents never hold credentials.",
    "saveOpenaiApiKey": "Secret keys never go through chat. Add your OpenAI key in Account → AI settings.",
    "saveApolloApiKey": "Secret keys never go through chat. Add your Apollo.io key in Account → AI settings.",
    "connectIntegration": "Takes raw OAuth tokens. Connect integrations from Account → Integrations in the app, where the provider's sign-in runs.",
    "runBackgroundTasks": "Superseded by enqueue_background_tasks, which is durable and deduplicated.",
    "grantStandingAuthorization": "Only the person can give Manifest standing permission, in the Manifest app (Messages); agents can't grant themselves permission (ADR 0021).",
    "rest:upload-profile-picture": "Needs a file upload (multipart). Change your picture in Account → Profile.",
}

# Fields never selected into agent context, even when the person owns them.
SECRET_FIELDS = re.compile(
    r"\b(accessToken|refreshToken|mergeSecret|token|secret|apiKey|password|keyHash)\b(\s*\{[^{}]*\})?"
)

SCALARS = {
    "String": {"type": "string"},
    "ID": {"type": "string"},
    "Int": {"type": "integer"},
    "Float": {"type": "number"},
    "Boolean": {"type": "boolean"},
    "DateTime": {"type": "string", "format": "date-time"},
    "Date": {"type": "string", "format": "date"},
    "JSON": {},
}
REST_TYPES = {
    "string": {"type": "string"},
    "int": {"type": "integer"},
    "bool": {"type": "boolean"},
    "list": {"type": "array", "items": {"type": "string"}},
}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().replace("-", "_")


def title(name: str) -> str:
    words = snake(name).split("_")
    return (
        " ".join([words[0].capitalize(), *words[1:]]).replace("Bmc", "BMC").replace(" prd", " PRD")
    )


def named(type_str: str) -> str:
    return re.sub(r"[\[\]!]", "", type_str)


def schema_for(type_str: str, catalog: dict, depth: int = 0) -> dict:
    inner = type_str[:-1] if type_str.endswith("!") else type_str
    if inner.startswith("["):
        return {"type": "array", "items": schema_for(inner[1:-1], catalog, depth + 1)}
    name = named(inner)
    if name in SCALARS:
        return dict(SCALARS[name])
    if name in catalog.get("enums", {}):
        values = catalog["enums"][name]
        return {"type": "string", "enum": [v["name"] if isinstance(v, dict) else v for v in values]}
    definition = catalog.get("inputs", {}).get(name)
    if definition and depth < 4:
        props, required = {}, []
        for field in definition["fields"]:
            props[field["name"]] = schema_for(field["type"], catalog, depth + 1)
            if field.get("description"):
                props[field["name"]]["description"] = field["description"]
            if field["required"]:
                required.append(field["name"])
        out = {"type": "object", "properties": props, "additionalProperties": False}
        if required:
            out["required"] = required
        return out
    return {}


def strip_secrets(selection: str) -> str:
    text = SECRET_FIELDS.sub("", selection or "")
    text = re.sub(r"\w+\s*\{\s*\}", "", text)  # sub-selections left empty
    return re.sub(r"\s+", " ", text).strip()


def variable_type(arg: dict) -> str:
    """An argument with a default is optional: declare its variable nullable, so leaving it
    out uses the server's default (GraphQL allows this only where the argument has one)."""
    if arg.get("default") is not None and not arg["required"]:
        return arg["type"].removesuffix("!")
    return arg["type"]


def document(op: dict, selection: str) -> str:
    declared = ", ".join(f"${a['name']}: {variable_type(a)}" for a in op["args"])
    passed = ", ".join(f"{a['name']}: ${a['name']}" for a in op["args"])
    name = op["name"][:1].upper() + op["name"][1:]
    header = f"{op['kind']} {name}" + (f"({declared})" if declared else "")
    call = op["name"] + (f"({passed})" if passed else "")
    return f"{header} {{ {call}{(' ' + selection) if selection else ''} }}"


CONFIRM = {
    "type": "boolean",
    "description": "Set to true only after the person has seen exactly what this will do and said yes.",
}


def describe(base: str, *, kind: str, destructive: bool, admin: bool) -> str:
    text = " ".join(base.strip().replace("``", "`").split())
    if text and text[-1] not in ".!?":
        text += "."
    if admin:
        text += " Admins only; others get a permission error."
    if destructive:
        text += " Destructive or hard to undo: show the person what will change, ask, then call again with confirm: true."
    elif kind != "query":
        text += " Changes the person's Manifest account; say what you will do before calling."
    return text


def graphql_tools(catalog: dict) -> list[dict]:
    tools = []
    for op in catalog["operations"]:
        if op["name"] in EXCLUDED:
            continue
        props, required = {}, []
        for arg in op["args"]:
            prop = schema_for(arg["type"], catalog)
            if arg.get("description"):
                prop["description"] = arg["description"]
            if arg.get("default") is not None:
                prop["default"] = arg["default"]
            props[arg["name"]] = prop
            if arg["required"]:
                required.append(arg["name"])
        destructive = bool(op["destructive"])
        if destructive:
            props["confirm"] = CONFIRM
        schema = {"type": "object", "properties": props, "additionalProperties": False}
        if required:
            schema["required"] = required
        admin = op["name"].startswith("admin")
        verb = "Read" if op["kind"] == "query" else "Run"
        base = op["description"] or f"{verb} {title(op['name']).lower()} in Manifest."
        selection = strip_secrets(op["selection"])
        tools.append(
            {
                "name": snake(op["name"]),
                "title": title(op["name"]),
                "description": describe(
                    base, kind=op["kind"], destructive=destructive, admin=admin
                ),
                "inputSchema": schema,
                "annotations": {
                    "title": title(op["name"]),
                    "readOnlyHint": op["kind"] == "query",
                    "destructiveHint": destructive,
                    "idempotentHint": op["kind"] == "query",
                    "openWorldHint": op["name"]
                    in {
                        "sendMessage",
                        "startConversation",
                        "createPitchReelComment",
                        "resharePitchReel",
                        "togglePublishIdea",
                        "inviteCollaborator",
                        "submitContactForm",
                    },
                },
                "_call": {
                    "via": "graphql",
                    "field": op["name"],
                    "document": document(op, selection),
                    "variables": [a["name"] for a in op["args"]],
                },
            }
        )
    return tools


def rest_tools() -> list[dict]:
    tools = []
    for cmd in REST_COMMANDS:
        key = f"rest:{cmd.command.replace(' ', '-')}"
        if key in EXCLUDED or cmd.upload:
            continue
        name = snake(f"{cmd.group}_{cmd.name}" if cmd.name else cmd.group)
        props, required = {}, []
        for param in re.findall(r"{(\w+)}", cmd.path):
            props[param] = {"type": "string"}
            required.append(param)
        for flag in cmd.body:
            prop = dict(REST_TYPES.get(flag.type, {"type": "string"}))
            if flag.help:
                prop["description"] = flag.help
            props[flag.name] = prop
            if flag.required:
                required.append(flag.name)
        if cmd.destructive:
            props["confirm"] = CONFIRM
        schema = {"type": "object", "properties": props, "additionalProperties": False}
        if required:
            schema["required"] = required
        read_only = cmd.method == "GET"
        tools.append(
            {
                "name": name,
                "title": title(name),
                "description": describe(
                    cmd.help,
                    kind="query" if read_only else "mutation",
                    destructive=cmd.destructive,
                    admin=False,
                ),
                "inputSchema": schema,
                "annotations": {
                    "title": title(name),
                    "readOnlyHint": read_only,
                    "destructiveHint": cmd.destructive,
                    "idempotentHint": read_only,
                    "openWorldHint": False,
                },
                "_call": {
                    "via": "rest",
                    "method": cmd.method,
                    "path": cmd.path,
                    "body": [f.name for f in cmd.body],
                    "extras": cmd.extras,
                },
            }
        )
    return tools


def build() -> dict:
    catalog = json.loads(CATALOG.read_text())
    tools = graphql_tools(catalog) + rest_tools()
    names = [t["name"] for t in tools]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise SystemExit(f"duplicate tool names: {sorted(dupes)}")
    return {
        "generated_by": "scripts/generate_agent_tools.py",
        "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "excluded": EXCLUDED,
        "tools": sorted(tools, key=lambda t: t["name"]),
    }


def table(data: dict) -> str:
    rows = [
        "# Manifest agent tools",
        "",
        "Generated by `scripts/generate_agent_tools.py` from the GraphQL schema and the REST list. "
        "Do not edit by hand.",
        "",
        f"**{len(data['tools'])} tools** on `https://manifeststartup.com/mcp`, "
        f"{sum(t['annotations']['readOnlyHint'] for t in data['tools'])} read-only, "
        f"{sum(t['annotations']['destructiveHint'] for t in data['tools'])} that need `confirm: true`.",
        "",
        "| Tool | Kind | What it does |",
        "|---|---|---|",
    ]
    for tool in data["tools"]:
        kind = (
            "read"
            if tool["annotations"]["readOnlyHint"]
            else "confirm"
            if tool["annotations"]["destructiveHint"]
            else "write"
        )
        text = tool["description"].split(". ")[0].rstrip(".").replace("|", "\\|")
        rows.append(f"| `{tool['name']}` | {kind} | {text}. |")
    rows += ["", "## Not available to agents, and why", ""]
    for name, reason in data["excluded"].items():
        rows.append(f"- `{name.removeprefix('rest:')}`: {reason}")
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed files drift")
    ns = parser.parse_args()
    data = build()
    tools_json = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    outputs = {OUT: tools_json, VOICE_OUT: tools_json, TABLE: table(data)}
    if ns.check:
        stale = [
            str(p.relative_to(ROOT))
            for p, text in outputs.items()
            if not p.exists() or p.read_text() != text
        ]
        if stale:
            print(
                "Agent tools are stale; run python3 scripts/generate_agent_tools.py: "
                + ", ".join(stale),
                file=sys.stderr,
            )
            return 1
        print(f"agent tools up to date ({len(data['tools'])} tools)")
        return 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(f"wrote {len(data['tools'])} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
