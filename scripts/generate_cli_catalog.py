#!/usr/bin/env python3
"""Generate the Manifest CLI command catalog from the Strawberry GraphQL schema.

    .venv/bin/python scripts/generate_cli_catalog.py          # rewrite the catalog
    .venv/bin/python scripts/generate_cli_catalog.py --check  # fail if it is stale

Every query and mutation becomes one ``manifest <kebab-name>`` command with flags
from its arguments and a default selection set (scalar fields to depth 2). The
catalog also records a hash of the schema SDL, so *any* schema change needs a
regenerated catalog: ``scripts/check.py`` (area ``cli``) and
``tests/test_cli_catalog.py`` fail until it is committed. Production disables
introspection, so the CLI ships this catalog instead of discovering the schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "mcp_server" / "src" / "manifest_cli" / "catalog.json"
CATALOG_VERSION = 1
MAX_DEPTH = 2

# Mutations that delete, revoke, spend or change who can see or own something
# ask for confirmation (or --yes) before they run.
_DESTRUCTIVE = re.compile(
    r"(?:^|_)(?:delete|deletion|remove|revoke|invest|investment|contribution|payment|pay|"
    r"disconnect|unfollow|restore|logout|erase|withdraw)(?:_|$)"
)
_DESTRUCTIVE_EXTRA = {
    "admin_set_user_role",
    "update_collaborator_role",
    "toggle_publish_idea",
    # GitHub: merging, visibility/rename/archive and raw API calls change real code.
    "github_merge_pull_request",
    "github_update_repo",
    "github_api_request",
}
# Commands the CLI itself owns; a schema field with one of these names would be shadowed.
RESERVED_COMMANDS = {
    "login",
    "logout",
    "whoami",
    "commands",
    "graphql",
    "api",
    "completion",
    "help",
    # REST command groups (manifest_cli/rest.py)
    "keys",
    "privacy",
    "dsar",
    "upload-profile-picture",
    "github-bootstrap",
    "github",
    "voice-capabilities",
    "trust-center",
}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def kebab(name: str) -> str:
    return _snake(name).replace("_", "-")


def _load_schema():
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    sys.path.insert(0, str(ROOT / "backend"))
    logging.disable(logging.CRITICAL)
    try:
        from app.graphql.schema import schema
    finally:
        logging.disable(logging.NOTSET)
    return schema


def _docstrings(schema) -> dict[tuple[str, str], str]:
    """Resolver docstrings, used when a field has no GraphQL description."""
    docs: dict[tuple[str, str], str] = {}
    for type_name in ("Query", "Mutation"):
        definition = schema.get_type_by_name(type_name)
        for field in getattr(definition, "fields", []) or []:
            resolver = getattr(field, "base_resolver", None)
            doc = (getattr(getattr(resolver, "wrapped_func", None), "__doc__", None) or "").strip()
            if doc:
                gql_name = schema.config.name_converter.from_field(field)
                docs[(type_name, gql_name)] = " ".join(doc.split("\n\n")[0].split())
    return docs


def _type_str(gql_type) -> str:
    return str(gql_type)


def _named(gql_type):
    from graphql import get_named_type

    return get_named_type(gql_type)


def _arg_kind(gql_type) -> str:
    from graphql import (
        GraphQLEnumType,
        GraphQLInputObjectType,
        GraphQLList,
        GraphQLNonNull,
    )

    inner = gql_type.of_type if isinstance(gql_type, GraphQLNonNull) else gql_type
    if isinstance(inner, GraphQLList):
        return "list"
    named = _named(gql_type)
    if isinstance(named, GraphQLInputObjectType):
        return "input"
    if isinstance(named, GraphQLEnumType):
        return "enum"
    return "scalar"


def _is_leaf(gql_type) -> bool:
    from graphql import is_leaf_type

    return is_leaf_type(_named(gql_type))


def _has_required_args(field) -> bool:
    return any(_required(a) for a in (field.args or {}).values())


def _required(arg_or_field) -> bool:
    """Non-null with no default value (graphql-core marks "no default" as Undefined)."""
    from graphql import GraphQLNonNull, Undefined

    return isinstance(arg_or_field.type, GraphQLNonNull) and arg_or_field.default_value is Undefined


def _selection(gql_type, depth: int = 1) -> str:
    """Scalar fields to MAX_DEPTH; '' for leaf return types."""
    from graphql import GraphQLInterfaceType, GraphQLObjectType, GraphQLUnionType

    named = _named(gql_type)
    if _is_leaf(gql_type):
        return ""
    if isinstance(named, GraphQLUnionType):
        parts = ["__typename"]
        for member in named.types:
            inner = _selection(member, depth)
            if inner:
                parts.append(f"... on {member.name} {inner}")
        return "{ " + " ".join(parts) + " }"
    if not isinstance(named, GraphQLObjectType | GraphQLInterfaceType):
        return ""
    parts: list[str] = []
    for name, field in named.fields.items():
        if _has_required_args(field):
            continue
        if _is_leaf(field.type):
            parts.append(name)
        elif depth < MAX_DEPTH:
            inner = _selection(field.type, depth + 1)
            if inner:
                parts.append(f"{name} {inner}")
    if not parts:
        return "{ __typename }"
    return "{ " + " ".join(parts) + " }"


def _value(value: Any) -> Any:
    from graphql import Undefined

    if value is Undefined:
        return None
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def build_catalog(schema=None) -> dict[str, Any]:
    from graphql import GraphQLEnumType, GraphQLInputObjectType

    schema = schema or _load_schema()
    gql = schema._schema
    sdl = schema.as_str()
    docs = _docstrings(schema)
    operations: list[dict[str, Any]] = []
    inputs: dict[str, Any] = {}
    enums: dict[str, list[str]] = {}

    def remember(gql_type) -> None:
        named = _named(gql_type)
        if isinstance(named, GraphQLEnumType) and named.name not in enums:
            enums[named.name] = list(named.values)
        if isinstance(named, GraphQLInputObjectType) and named.name not in inputs:
            inputs[named.name] = {}
            fields = []
            for fname, f in named.fields.items():
                fields.append(
                    {
                        "name": fname,
                        "type": _type_str(f.type),
                        "required": _required(f),
                        "description": f.description or "",
                    }
                )
                remember(f.type)
            inputs[named.name] = {"description": named.description or "", "fields": fields}

    for kind, root in (("query", gql.query_type), ("mutation", gql.mutation_type)):
        if root is None:
            continue
        type_name = "Query" if kind == "query" else "Mutation"
        for name, field in root.fields.items():
            snake = _snake(name)
            command = kebab(name)
            if command in RESERVED_COMMANDS:
                raise SystemExit(f"GraphQL field {name} collides with the CLI command {command}")
            args = []
            for arg_name, arg in (field.args or {}).items():
                remember(arg.type)
                args.append(
                    {
                        "name": arg_name,
                        "flag": "--" + kebab(arg_name),
                        "type": _type_str(arg.type),
                        "kind": _arg_kind(arg.type),
                        "required": _required(arg),
                        "default": _value(arg.default_value),
                        "description": arg.description or "",
                    }
                )
            description = field.description or docs.get((type_name, name)) or ""
            operations.append(
                {
                    "name": name,
                    "command": command,
                    "kind": kind,
                    "description": description,
                    "destructive": kind == "mutation"
                    and (bool(_DESTRUCTIVE.search(snake)) or snake in _DESTRUCTIVE_EXTRA),
                    "returns": _type_str(field.type),
                    "selection": _selection(field.type),
                    "args": args,
                }
            )

    return {
        "version": CATALOG_VERSION,
        "generated_by": "scripts/generate_cli_catalog.py",
        "schema_sha256": hashlib.sha256(sdl.encode()).hexdigest(),
        "operations": operations,
        "inputs": dict(sorted(inputs.items())),
        "enums": dict(sorted(enums.items())),
    }


def render(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the committed catalog is stale"
    )
    parser.add_argument("--output", type=Path, default=CATALOG)
    args = parser.parse_args(argv)
    text = render(build_catalog())
    if args.check:
        current = args.output.read_text() if args.output.exists() else ""
        if current != text:
            print(
                f"{args.output.relative_to(ROOT)} is stale: the GraphQL schema changed.\n"
                "Regenerate it: .venv/bin/python scripts/generate_cli_catalog.py",
                file=sys.stderr,
            )
            return 1
        ops = json.loads(text)["operations"]
        print(f"CLI catalog up to date ({len(ops)} operations)")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    ops = json.loads(text)["operations"]
    queries = sum(1 for o in ops if o["kind"] == "query")
    print(
        f"wrote {args.output.relative_to(ROOT)}: {queries} queries, {len(ops) - queries} mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
