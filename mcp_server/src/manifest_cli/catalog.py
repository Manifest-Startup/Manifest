"""Turn the generated GraphQL catalog (``catalog.json``) into CLI commands.

``scripts/generate_cli_catalog.py`` writes the catalog from the backend schema; this
module only reads it, so the CLI works against production, where introspection is off.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any


class UsageError(Exception):
    """A command line the CLI can explain (exit code 2)."""


@cache
def load_catalog() -> dict[str, Any]:
    text = resources.files("manifest_cli").joinpath("catalog.json").read_text(encoding="utf-8")
    return json.loads(text)


def operations() -> list[dict[str, Any]]:
    return load_catalog()["operations"]


def find(command: str) -> dict[str, Any] | None:
    return next((op for op in operations() if op["command"] == command), None)


def kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower().replace("_", "-")


def named_type(type_str: str) -> str:
    return re.sub(r"[\[\]!]", "", type_str)


def is_list(type_str: str) -> bool:
    return type_str.rstrip("!").startswith("[")


def describe(op: dict[str, Any]) -> str:
    text = op.get("description") or (
        f"{'Read' if op['kind'] == 'query' else 'Run'} the `{op['name']}` GraphQL {op['kind']}."
    )
    return text


# -- values --------------------------------------------------------------------


def read_json_argument(raw: str, *, what: str) -> Any:
    """``-`` reads stdin, ``@path`` reads a file, anything else is inline JSON."""
    if raw == "-":
        text = sys.stdin.read()
    elif raw.startswith("@"):
        try:
            text = Path(raw[1:]).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"{what}: cannot read {raw[1:]}: {exc.strerror}") from None
    else:
        text = raw
    try:
        return json.loads(text)
    except ValueError as exc:
        raise UsageError(f"{what}: expected JSON ({exc})") from None


def _scalar(raw: Any, type_name: str, *, what: str) -> Any:
    if not isinstance(raw, str):
        return raw
    enums = load_catalog().get("enums", {})
    try:
        if type_name == "Int":
            return int(raw)
        if type_name == "Float":
            return float(raw)
    except ValueError:
        raise UsageError(f"{what}: expected {type_name}, got {raw!r}") from None
    if type_name == "Boolean":
        lowered = raw.lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
        raise UsageError(f"{what}: expected true or false, got {raw!r}")
    if type_name in enums:
        if raw not in enums[type_name]:
            raise UsageError(f"{what}: expected one of {', '.join(enums[type_name])}")
        return raw
    if type_name in {"String", "ID", "DateTime", "Date", "Time", "UUID", "Decimal"}:
        return raw
    if type_name in load_catalog().get("inputs", {}) or type_name == "JSON":
        return read_json_argument(raw, what=what)
    return raw


def convert(raw: Any, type_str: str, *, what: str) -> Any:
    """Convert a flag value (or list of repeated values) to the GraphQL variable value."""
    base = named_type(type_str)
    if is_list(type_str):
        values = raw if isinstance(raw, list) else [raw]
        if len(values) == 1 and isinstance(values[0], str) and values[0][:1] in "[@-":
            parsed = read_json_argument(values[0], what=what)
            values = parsed if isinstance(parsed, list) else [parsed]
        return [_scalar(v, base, what=what) for v in values]
    return _scalar(raw, base, what=what)


# -- argparse ------------------------------------------------------------------


def _dest(name: str) -> str:
    return "arg__" + name


def _field_dest(arg: str, field: str) -> str:
    return f"field__{arg}__{field}"


def add_operation_arguments(parser: argparse.ArgumentParser, op: dict[str, Any]) -> None:
    """Flags from the operation's arguments (plus flattened input-object fields)."""
    inputs = load_catalog().get("inputs", {})
    group = parser.add_argument_group("arguments")
    taken = {a.option_strings[0] for a in parser._actions if a.option_strings}  # noqa: SLF001
    for arg in op["args"]:
        flag = arg["flag"]
        taken.add(flag)
        hint = arg["type"]
        if arg["kind"] in {"input", "list"}:
            hint += " (JSON, @file or - for stdin)"
        if arg["required"]:
            hint += " (required)"
        if arg.get("default") is not None:
            hint += f"; default {arg['default']}"
        if arg.get("description"):
            hint = f"{arg['description']} [{hint}]"
        kwargs: dict[str, Any] = {"dest": _dest(arg["name"]), "help": hint, "metavar": "VALUE"}
        if arg["kind"] == "list":
            kwargs["action"] = "append"
        elif named_type(arg["type"]) == "Boolean":
            kwargs.update(nargs="?", const="true", metavar="true|false")
        group.add_argument(flag, **kwargs)
    for arg in op["args"]:
        definition = inputs.get(named_type(arg["type"])) if arg["kind"] == "input" else None
        if definition:
            _add_input_field_flags(parser, arg, definition, taken)


def _add_input_field_flags(
    parser: argparse.ArgumentParser,
    arg: dict[str, Any],
    definition: dict[str, Any],
    taken: set[str],
) -> None:
    """``--first-name`` etc. for the fields of an input-object argument."""
    fields_group = parser.add_argument_group(
        f"{arg['flag']} fields",
        f"Set fields of {arg['type']} one by one (merged over {arg['flag']}).",
    )
    for field in definition["fields"]:
        flag = "--" + kebab(field["name"])
        if flag in taken:
            continue
        taken.add(flag)
        kwargs: dict[str, Any] = {
            "dest": _field_dest(arg["name"], field["name"]),
            "help": field.get("description") or field["type"],
            "metavar": "VALUE",
        }
        if is_list(field["type"]):
            kwargs["action"] = "append"
        elif named_type(field["type"]) == "Boolean":
            kwargs.update(nargs="?", const="true", metavar="true|false")
        fields_group.add_argument(flag, **kwargs)


def variables_from_args(op: dict[str, Any], ns: argparse.Namespace) -> dict[str, Any]:
    """Collect GraphQL variables: ``--variables`` JSON, then flags, then input fields."""
    inputs = load_catalog().get("inputs", {})
    variables: dict[str, Any] = {}
    if getattr(ns, "variables", None):
        loaded = read_json_argument(ns.variables, what="--variables")
        if not isinstance(loaded, dict):
            raise UsageError("--variables must be a JSON object")
        variables.update(loaded)
    for arg in op["args"]:
        raw = getattr(ns, _dest(arg["name"]), None)
        if raw is not None:
            variables[arg["name"]] = convert(raw, arg["type"], what=arg["flag"])
        definition = inputs.get(named_type(arg["type"])) if arg["kind"] == "input" else None
        if definition:
            for field in definition["fields"]:
                value = getattr(ns, _field_dest(arg["name"], field["name"]), None)
                if value is None:
                    continue
                target = variables.setdefault(arg["name"], {})
                if not isinstance(target, dict):
                    raise UsageError(f"{arg['flag']} must be a JSON object to add fields to it")
                target[field["name"]] = convert(
                    value, field["type"], what="--" + kebab(field["name"])
                )
    missing = [a["flag"] for a in op["args"] if a["required"] and a["name"] not in variables]
    if missing:
        raise UsageError(f"missing required {', '.join(missing)}")
    return variables


def normalize_selection(selection: str | None) -> str:
    text = (selection or "").strip()
    if not text:
        return ""
    return text if text.startswith("{") else "{ " + text + " }"


def build_document(
    op: dict[str, Any], variables: dict[str, Any], selection: str | None = None
) -> str:
    """``query Name($a: T!) { field(a: $a) { …selection… } }`` for the provided variables."""
    used = [a for a in op["args"] if a["name"] in variables]
    declared = ", ".join(f"${a['name']}: {a['type']}" for a in used)
    passed = ", ".join(f"{a['name']}: ${a['name']}" for a in used)
    name = op["name"][:1].upper() + op["name"][1:]
    header = f"{op['kind']} {name}" + (f"({declared})" if declared else "")
    call = op["name"] + (f"({passed})" if passed else "")
    chosen = normalize_selection(selection) if selection is not None else op["selection"]
    return f"{header} {{ {call}{(' ' + chosen) if chosen else ''} }}"
