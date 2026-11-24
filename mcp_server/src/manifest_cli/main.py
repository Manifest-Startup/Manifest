"""``manifest``: everything you can do in Manifest, from the terminal.

Every GraphQL query and mutation is a command (generated into ``catalog.json``),
plus sign-in, the useful REST areas, raw ``graphql`` / ``api`` escape hatches and
shell completion. See ``manifest commands`` and ``docs/CLI.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import quote

import httpx
from manifest_mcp.client import ManifestClient

from manifest_cli import __version__, auth, catalog, config, output, rest
from manifest_cli.catalog import UsageError

BUILTINS: dict[str, str] = {
    "login": "Sign in: approve this computer in your browser.",
    "logout": "Revoke this computer's CLI session and forget it.",
    "whoami": "Show who you are signed in as, and where.",
    "voice": "Talk to Manifest out loud: it can do everything the CLI can.",
    "bridge": "Let the Manifest app use Claude Code or Codex on this computer (no OpenAI key).",
    "vault-folder": "Show or move this computer's vault folder: manifest vault-folder icloud.",
    "github": "Connect your GitHub (manifest github connect), see it, or disconnect it.",
    "commands": "List every command (filter with --search).",
    "graphql": "Run any GraphQL document (escape hatch).",
    "api": "Call any REST endpoint: manifest api GET /api/keys/usage.",
    "completion": "Print a shell completion script: manifest completion zsh|bash.",
}


STEP_UP_HINT = "Run `manifest login` again to confirm it's you, then retry within 5 minutes."


class CliError(Exception):
    """A failure the CLI reports on stderr with exit code 1."""


class Context:
    def __init__(
        self,
        out: TextIO,
        err: TextIO,
        stdin: TextIO,
        transport: httpx.AsyncBaseTransport | None,
        open_url: Callable[[str], None] | None,
    ):
        self.out, self.err, self.stdin = out, err, stdin
        self.transport = transport
        self.open_url = open_url

    def client(self, ns: argparse.Namespace, *, with_token: bool = True) -> ManifestClient:
        token = config.token(getattr(ns, "token", None)) if with_token else None
        return ManifestClient(
            base_url=config.base_url(getattr(ns, "base_url", None)),
            auth_token=token,
            timeout=120.0,
            user_agent=f"manifest-cli/{__version__}",
            transport=self.transport,
        )


# -- parsers -------------------------------------------------------------------


def _common() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    group = common.add_argument_group("global options")
    group.add_argument(
        "--base-url", help="Manifest URL (default: saved login, then $MANIFEST_API_URL)"
    )
    group.add_argument("--token", help=argparse.SUPPRESS)
    group.add_argument("--json", action="store_true", help="print raw JSON")
    return common


def _sub(name: str, description: str, *, epilog: str | None = None) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog=f"manifest {name}",
        description=description,
        epilog=epilog,
        parents=[_common()],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def operation_parser(op: dict[str, Any]) -> argparse.ArgumentParser:
    lines = [catalog.describe(op), "", f"GraphQL {op['kind']} `{op['name']}` → {op['returns']}"]
    if op["destructive"]:
        lines.append("Asks for confirmation; pass --yes to skip the prompt.")
    if op["selection"]:
        lines += ["", f"Default fields: {op['selection']}"]
    example = " ".join(
        [f"manifest {op['command']}"] + [f"{a['flag']} …" for a in op["args"] if a["required"]]
    )
    parser = _sub(op["command"], "\n".join(lines), epilog=f"example:\n  {example}")
    add = parser.add_argument_group("command options")
    add.add_argument(
        "--select", help="fields to return, e.g. 'ideaId title' (overrides the default)"
    )
    add.add_argument("--variables", help="all variables as JSON, @file or - (flags win)")
    add.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    add.add_argument(
        "--print-query", action="store_true", help="print the GraphQL document and exit"
    )
    catalog.add_operation_arguments(parser, op)
    return parser


def rest_parser(cmd: rest.RestCommand) -> argparse.ArgumentParser:
    extra = "\nAsks for confirmation; pass --yes to skip the prompt." if cmd.destructive else ""
    parser = _sub(cmd.command, f"{cmd.help}\n\n{cmd.method} {cmd.path}{extra}")
    for param in rest.path_params(cmd):
        parser.add_argument(param, help=param.replace("_", " "))
    if cmd.upload:
        parser.add_argument("file", help="file to upload")
    for flag in cmd.body:
        kwargs: dict[str, Any] = {"dest": "body__" + flag.name, "help": flag.help or flag.type}
        if flag.type == "list":
            kwargs["action"] = "append"
        elif flag.type == "bool":
            kwargs.update(nargs="?", const="true", metavar="true|false")
        elif flag.type == "int":
            kwargs["type"] = int
        parser.add_argument("--" + flag.name.replace("_", "-"), **kwargs)
    if cmd.body_input:
        parser.add_argument("--input", help="whole JSON body, @file or - (flags win)")
    parser.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    return parser


def top_help() -> str:
    ops = catalog.operations()
    queries = sum(1 for op in ops if op["kind"] == "query")
    lines = [
        f"manifest {__version__}: everything you can do in Manifest, from the terminal.",
        "",
        "usage: manifest <command> [options]   (manifest <command> --help for details)",
        "",
        "Getting started:",
    ]
    lines += [f"  {name:<12} {text}" for name, text in BUILTINS.items()]
    lines += ["", "REST areas:"]
    for group, cmds in rest.groups().items():
        subs = ", ".join(c.name for c in cmds if c.name)
        lines.append(f"  {group:<22} {subs or cmds[0].help}")
    lines += [
        "",
        f"GraphQL: {queries} queries and {len(ops) - queries} mutations, one command each "
        "(e.g. manifest ideas, manifest create-idea --title …).",
        "Run `manifest commands` to list them all, or `manifest commands --search idea`.",
    ]
    return "\n".join(lines) + "\n"


# -- helpers -------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _confirm(ctx: Context, ns: argparse.Namespace, what: str) -> None:
    if getattr(ns, "yes", False):
        return
    if not ctx.stdin.isatty():
        raise UsageError(f"{what} is destructive; pass --yes to run it without a prompt")
    ctx.err.write(f"{what}: this can't be undone easily. Continue? [y/N] ")
    ctx.err.flush()
    answer = ctx.stdin.readline().strip().lower()
    if answer not in {"y", "yes"}:
        raise CliError("cancelled")


def _http_error(response: httpx.Response) -> CliError:
    try:
        body = response.json()
    except ValueError:
        body = response.text[:300]
    detail = (
        body.get("detail") or body.get("error_description") or body
        if isinstance(body, dict)
        else body
    )
    message = (
        f"HTTP {response.status_code}: {detail if isinstance(detail, str) else json.dumps(detail)}"
    )
    if response.status_code in (401, 403) and response.headers.get("X-Step-Up-Required"):
        message += f"\n{STEP_UP_HINT}"
    elif response.status_code == 401:
        message += "\nNot signed in, or the session expired. Run `manifest login`."
    return CliError(message)


async def _graphql(ctx: Context, ns: argparse.Namespace, document: str, variables: dict | None):
    async with ctx.client(ns) as client:
        return await client.graphql(document, variables)


def _report_graphql(
    ctx: Context, ns: argparse.Namespace, body: dict[str, Any], field: str | None
) -> int:
    data = body.get("data")
    errors = body.get("errors") or []
    value = data.get(field) if field and isinstance(data, dict) else data
    if value is not None or not errors:
        output.emit(value, as_json=ns.json, out=ctx.out)
    for error in errors:
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        ctx.err.write(f"error: {message}\n")
        if any(
            word in message.lower() for word in ("missing token", "expired", "not authenticated")
        ):
            ctx.err.write("Run `manifest login` to sign in.\n")
    return 1 if errors else 0


# -- commands ------------------------------------------------------------------


def cmd_operation(ctx: Context, op: dict[str, Any], argv: list[str]) -> int:
    ns = operation_parser(op).parse_args(argv)
    variables = catalog.variables_from_args(op, ns)
    document = catalog.build_document(op, variables, ns.select)
    if ns.print_query:
        ctx.out.write(document + "\n")
        if variables:
            ctx.out.write(json.dumps(variables, indent=2) + "\n")
        return 0
    if op["destructive"]:
        _confirm(ctx, ns, f"manifest {op['command']}")
    body = _run(_graphql(ctx, ns, document, variables))
    return _report_graphql(ctx, ns, body, op["name"])


def cmd_graphql(ctx: Context, argv: list[str]) -> int:
    parser = _sub("graphql", BUILTINS["graphql"])
    parser.add_argument("document", help="GraphQL document, @file or - for stdin")
    parser.add_argument("--variables", help="variables as JSON, @file or -")
    ns = parser.parse_args(argv)
    document = ns.document
    if document == "-":
        document = ctx.stdin.read()
    elif document.startswith("@"):
        try:
            with open(document[1:], encoding="utf-8") as handle:
                document = handle.read()
        except OSError as exc:
            raise UsageError(f"cannot read {document[1:]}: {exc.strerror}") from None
    variables = (
        catalog.read_json_argument(ns.variables, what="--variables") if ns.variables else None
    )
    if variables is not None and not isinstance(variables, dict):
        raise UsageError("--variables must be a JSON object")
    body = _run(_graphql(ctx, ns, document, variables))
    return _report_graphql(ctx, ns, body, None)


async def _rest_call(
    ctx: Context,
    ns: argparse.Namespace,
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    async with ctx.client(ns) as client:
        response = await client.request(method, path, json=json_body, params=params, files=files)
    if response.status_code >= 400:
        raise _http_error(response)
    if not response.content:
        return {"ok": True, "status": response.status_code}
    try:
        return response.json()
    except ValueError:
        return response.text


def cmd_api(ctx: Context, argv: list[str]) -> int:
    parser = _sub("api", BUILTINS["api"], epilog="example:\n  manifest api GET /api/keys/usage")
    parser.add_argument("method", type=str.upper, choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    parser.add_argument("path", help="path starting with / (e.g. /api/keys/clients)")
    parser.add_argument("--data", "-d", help="JSON body, @file or -")
    parser.add_argument(
        "--query", "-q", action="append", default=[], help="query parameter key=value"
    )
    parser.add_argument("--yes", "-y", action="store_true", help="do not ask before DELETE")
    ns = parser.parse_args(argv)
    if not ns.path.startswith("/"):
        raise UsageError("path must start with /")
    params = {}
    for item in ns.query:
        key, sep, value = item.partition("=")
        if not sep:
            raise UsageError(f"--query expects key=value, got {item!r}")
        params[key] = value
    body = catalog.read_json_argument(ns.data, what="--data") if ns.data else None
    if ns.method == "DELETE":
        _confirm(ctx, ns, f"DELETE {ns.path}")
    result = _run(_rest_call(ctx, ns, ns.method, ns.path, json_body=body, params=params or None))
    output.emit(result, as_json=ns.json, out=ctx.out)
    return 0


def cmd_rest(ctx: Context, cmd: rest.RestCommand, argv: list[str]) -> int:
    ns = rest_parser(cmd).parse_args(argv)
    path = cmd.path
    for param in rest.path_params(cmd):
        path = path.replace("{" + param + "}", quote(getattr(ns, param), safe=""))
    body: dict[str, Any] | None = None
    if cmd.body or cmd.body_input:
        body = {}
        if getattr(ns, "input", None):
            loaded = catalog.read_json_argument(ns.input, what="--input")
            if not isinstance(loaded, dict):
                raise UsageError("--input must be a JSON object")
            body.update(loaded)
        for flag in cmd.body:
            value = getattr(ns, "body__" + flag.name)
            if value is None:
                if flag.required and flag.name not in body:
                    raise UsageError(f"missing required --{flag.name.replace('_', '-')}")
                continue
            body[flag.name] = (
                catalog.convert(value, "Boolean", what=flag.name) if flag.type == "bool" else value
            )
        body.update(cmd.extras)
    files = None
    if cmd.upload:
        try:
            handle = open(ns.file, "rb")  # noqa: SIM115 - closed below
        except OSError as exc:
            raise UsageError(f"cannot read {ns.file}: {exc.strerror}") from None
        files = {cmd.upload: (ns.file.rsplit("/", 1)[-1], handle)}
    if cmd.destructive:
        _confirm(ctx, ns, f"manifest {cmd.command}")
    try:
        result = _run(_rest_call(ctx, ns, cmd.method, path, json_body=body, files=files))
    finally:
        if files:
            files[cmd.upload][1].close()
    output.emit(result, as_json=ns.json, out=ctx.out)
    return 0


def cmd_rest_group(ctx: Context, group: str, argv: list[str]) -> int:
    cmds = rest.groups()[group]
    if len(cmds) == 1 and not cmds[0].name:
        return cmd_rest(ctx, cmds[0], argv)
    by_name = {c.name: c for c in cmds}
    if not argv or argv[0] in {"-h", "--help"} or argv[0] not in by_name:
        if argv and argv[0] not in {"-h", "--help"}:
            ctx.err.write(f"unknown command: manifest {group} {argv[0]}\n")
        ctx.out.write(f"usage: manifest {group} <command> [options]\n\n")
        for c in cmds:
            mark = " (asks first)" if c.destructive else ""
            ctx.out.write(f"  {c.name:<22} {c.help}{mark}\n")
        return 0 if not argv or argv[0] in {"-h", "--help"} else 2
    return cmd_rest(ctx, by_name[argv[0]], argv[1:])


def cmd_commands(ctx: Context, argv: list[str]) -> int:
    parser = _sub("commands", BUILTINS["commands"])
    parser.add_argument("--search", "-s", help="only commands whose name or description match")
    parser.add_argument("--kind", choices=["query", "mutation", "rest", "builtin"])
    ns = parser.parse_args(argv)
    rows: list[dict[str, Any]] = []
    rows += [{"command": n, "kind": "builtin", "description": d} for n, d in BUILTINS.items()]
    rows += [
        {
            "command": c.command,
            "kind": "rest",
            "description": c.help + (" (asks first)" if c.destructive else ""),
        }
        for c in rest.REST_COMMANDS
    ]
    rows += [
        {
            "command": op["command"],
            "kind": op["kind"],
            "description": catalog.describe(op) + (" (asks first)" if op["destructive"] else ""),
        }
        for op in catalog.operations()
    ]
    if ns.kind:
        rows = [r for r in rows if r["kind"] == ns.kind]
    if ns.search:
        needle = ns.search.lower()
        rows = [r for r in rows if needle in r["command"] or needle in r["description"].lower()]
    if ns.json:
        output.emit(rows, as_json=True, out=ctx.out)
        return 0
    width = max((len(r["command"]) for r in rows), default=10)
    for r in rows:
        ctx.out.write(f"{r['command']:<{width}}  {r['kind']:<8}  {r['description']}\n")
    ctx.out.write(f"\n{len(rows)} commands\n")
    return 0


def cmd_login(ctx: Context, argv: list[str]) -> int:
    parser = _sub(
        "login",
        BUILTINS["login"]
        + "\n\nOpens Manifest in your browser. After you sign in with Open Media (passkeys and"
        "\nMFA apply) and click Allow, the CLI receives a session that lasts 30 days and"
        "\nshows up under Account → Security → Active sessions, where you can revoke it.",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="print the URL instead of opening it"
    )
    parser.add_argument(
        "--timeout", type=float, default=auth.LOGIN_TIMEOUT_SECONDS, help=argparse.SUPPRESS
    )
    ns = parser.parse_args(argv)
    base_url = config.base_url(ns.base_url)
    pkce = auth.new_pkce()
    opener = ctx.open_url or (
        lambda url: auth.open_in_browser(url, launch=not ns.no_browser, out=ctx.err)
    )
    try:
        code, redirect_uri = auth.wait_for_callback(
            pkce, opener, base_url=base_url, timeout=ns.timeout
        )
    except auth.LoginError as exc:
        raise CliError(str(exc)) from None

    async def exchange() -> httpx.Response:
        client = ManifestClient(
            base_url=base_url, user_agent=f"manifest-cli/{__version__}", transport=ctx.transport
        )
        async with client:
            return await client.request(
                "POST",
                "/api/cli/token",
                json={
                    "code": code,
                    "code_verifier": pkce.verifier,
                    "redirect_uri": redirect_uri,
                    "hostname": auth.hostname(),
                },
            )

    response = _run(exchange())
    if response.status_code >= 400:
        raise _http_error(response)
    grant = response.json()
    saved = config.load()
    saved.update(
        {
            "base_url": base_url,
            "token": grant["access_token"],
            "expires_at": grant.get("expires_at"),
            "label": grant.get("label"),
            "user": grant.get("user") or {},
        }
    )
    path = config.save(saved)
    who = (grant.get("user") or {}).get("email") or (grant.get("user") or {}).get("user_id")
    ctx.err.write(f"Signed in to {base_url} as {who}.\n")
    ctx.err.write(
        f'Session "{grant.get("label")}" saved to {path} (until {_day(grant.get("expires_at"))}).\n'
    )
    return 0


def _day(value: str | None) -> str:
    try:
        return datetime.fromisoformat(str(value)).date().isoformat()
    except ValueError:
        return str(value)


def cmd_logout(ctx: Context, argv: list[str]) -> int:
    ns = _sub("logout", BUILTINS["logout"]).parse_args(argv)
    saved = config.load()
    token = config.token(ns.token)
    if not token:
        ctx.err.write("Not signed in.\n")
        return 0
    # Only forget the saved login if that is the token being revoked; a --token or
    # MANIFEST_API_TOKEN override leaves cli.json alone.
    from_saved_file = bool(saved.get("token")) and token == saved.get("token")

    async def revoke() -> httpx.Response:
        async with ctx.client(ns) as client:
            return await client.request("POST", "/api/auth/logout")

    try:
        response = _run(revoke())
        revoked = response.status_code < 400
    except Exception as exc:  # noqa: BLE001 - still forget the token locally
        ctx.err.write(f"warning: could not reach Manifest to revoke the session: {exc}\n")
        revoked = False
    if from_saved_file:
        for key in ("token", "expires_at", "label", "user"):
            saved.pop(key, None)
        config.save(saved)
    if revoked:
        ctx.err.write("Signed out; the session was revoked.\n")
    else:
        ctx.err.write("Could not revoke the session on the server.\n")
    if not from_saved_file and saved.get("token"):
        ctx.err.write(f"The saved login in {config.config_path()} was left in place.\n")
    elif from_saved_file:
        ctx.err.write(f"Removed the saved login from {config.config_path()}.\n")
    return 0


def cmd_whoami(ctx: Context, argv: list[str]) -> int:
    ns = _sub("whoami", BUILTINS["whoami"]).parse_args(argv)
    if not config.token(ns.token):
        raise CliError("Not signed in. Run `manifest login`.")
    body = _run(_graphql(ctx, ns, "query WhoAmI { profile { userId email isGuest } }", None))
    profile = (body.get("data") or {}).get("profile")
    if not profile:
        for error in body.get("errors") or []:
            ctx.err.write(f"error: {error.get('message')}\n")
        raise CliError("The saved session is no longer valid. Run `manifest login`.")
    saved = config.load()
    info = {
        "email": profile.get("email"),
        "user_id": profile.get("userId"),
        "base_url": config.base_url(ns.base_url),
        "session": saved.get("label") if not ns.token else "(token from --token)",
        "expires_at": saved.get("expires_at"),
    }
    output.emit(info, as_json=ns.json, out=ctx.out)
    return 0


def cmd_voice(ctx: Context, argv: list[str]) -> int:
    from manifest_cli import voice

    parser = _sub(
        "voice",
        BUILTINS["voice"],
        epilog="Speech, the model and Manifest's tools run on the server with your own OpenAI key.\n"
        "The mic is muted while Manifest speaks; use --barge-in with headphones to interrupt it.\n"
        "With --agent, your own agent (Claude Code, Codex, ...) answers on this computer and\n"
        "Manifest only listens and speaks: manifest voice --agent claude --continue",
    )
    parser.add_argument("--text", action="store_true", help="type instead of speaking")
    parser.add_argument(
        "--barge-in", action="store_true", help="keep the mic on while Manifest speaks"
    )
    parser.add_argument(
        "--agent",
        metavar="AGENT",
        help="your own agent answers instead: claude (Claude Code), codex, or a command "
        "that reads the turn on stdin and prints the reply",
    )
    parser.add_argument(
        "--continue",
        dest="continue_last",
        action="store_true",
        help="with --agent: continue its newest session in this folder (incl. VS Code)",
    )
    parser.add_argument("--resume", metavar="SESSION", help="with --agent: resume this session")
    parser.add_argument(
        "--agent-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="extra argument for the agent, repeatable (e.g. --agent-arg=--permission-mode=acceptEdits)",
    )
    ns = parser.parse_args(argv)
    token = config.token(ns.token)
    if not token:
        raise CliError("Not signed in. Run `manifest login`.")
    if not ns.text:
        problem = voice.missing_audio_support()
        if problem:
            raise CliError(problem)
    agent = None
    if ns.agent:
        from manifest_cli.agents import make_agent, missing_agent

        agent = make_agent(
            ns.agent, extra_args=ns.agent_arg, resume=ns.resume, continue_last=ns.continue_last
        )
        problem = missing_agent(agent)
        if problem:
            raise CliError(problem)
        from pathlib import Path as _Path

        from manifest_cli import bridge_setup

        if ns.agent.strip().lower() == "codex" and not bridge_setup.codex_trusts(_Path.cwd()):
            raise CliError(
                "Codex only answers inside a project it trusts (a Git repository). "
                "Run this from your project folder."
            )
    elif ns.continue_last or ns.resume or ns.agent_arg:
        raise CliError("--continue, --resume and --agent-arg go with --agent.")
    return voice.run(
        config.base_url(ns.base_url),
        token,
        out=ctx.out,
        stdin=ctx.stdin,
        text_mode=ns.text,
        barge_in=ns.barge_in,
        agent=agent,
    )


def cmd_vault_folder(ctx: Context, argv: list[str]) -> int:
    from manifest_cli import vault_folder

    parser = _sub(
        "vault-folder",
        BUILTINS["vault-folder"],
        epilog="With no place, shows where the vault is. A place moves the whole folder there\n"
        "(nothing is deleted), restarts background sync and remembers it for the app,\n"
        "voice and agents. Examples: manifest vault-folder icloud · manifest vault-folder\n"
        "~/Dropbox/Notes",
    )
    parser.add_argument("place", nargs="?", help="icloud, documents, home, or a full path")
    parser.add_argument(
        "--on-delete",
        choices=vault_folder.ON_DELETE,
        help="when a note is deleted in Manifest: delete it here too (default) or keep a copy",
    )
    ns = parser.parse_args(argv)
    try:
        if ns.on_delete:
            result = vault_folder.set_on_delete(ns.on_delete)
            if ns.place:
                result = vault_folder.move(ns.place)
        else:
            result = vault_folder.move(ns.place) if ns.place else vault_folder.where()
    except vault_folder.VaultFolderError as exc:
        raise CliError(str(exc)) from exc
    if ns.json:
        ctx.out.write(json.dumps(result) + "\n")
    elif ns.place:
        verb = "Moved your vault to" if result.get("moved") else "Your vault is at"
        ctx.out.write(f"{verb} {result['folder']}\n")
        if result.get("warning"):
            ctx.out.write(f"{result['warning']}\n")
    else:
        ctx.out.write(f"{result['folder']}\n")
        if result.get("icloud"):
            ctx.out.write("It's in iCloud Drive, so it's on your other Apple devices too.\n")
    if not ns.json and result.get("on_delete"):
        ctx.out.write(
            "Notes deleted in Manifest are deleted here too.\n"
            if result["on_delete"] == "delete"
            else "Notes deleted in Manifest stay here as your copies.\n"
        )
    return 0


GITHUB_ACCOUNT_FIELDS = (
    "connected oauthAvailable login name htmlUrl scopes method connectUrl message"
)


def _gh_cli_token() -> str | None:
    """The GitHub CLI's token for github.com, when `gh` is installed and signed in."""
    import shutil
    import subprocess

    if not shutil.which("gh"):
        return None
    try:
        done = subprocess.run(
            ["gh", "auth", "token", "--hostname", "github.com"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = done.stdout.strip()
    return token if done.returncode == 0 and token else None


# Where a GitHub login may already live on this computer, so nobody connects twice:
# the GitHub CLI, then the variables the GitHub plugin / GitHub MCP server and other tools read.
GITHUB_TOKEN_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN")


def _existing_github_login() -> tuple[str, str] | None:
    """(token, where it came from) for a GitHub login already on this computer."""
    import os

    token = _gh_cli_token()
    if token:
        return token, "the GitHub CLI's login"
    for name in GITHUB_TOKEN_ENV:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value, f"${name}"
    return None


def _github_token(ctx: Context, ns: argparse.Namespace) -> tuple[str, str]:
    """The token to connect with, and where it came from ("gh" or "token")."""
    if ns.token_stdin:
        return ctx.stdin.read().strip(), ""
    if not ns.no_gh:
        found = _existing_github_login()
        if found:
            return found
    if not ctx.stdin.isatty():
        raise CliError(
            "No GitHub login found on this computer. Sign in to the GitHub CLI "
            "(`gh auth login`) and run this again, or pipe a token in with --token-stdin."
        )
    import getpass

    ctx.err.write(
        "Create a token at https://github.com/settings/tokens (classic: repo, workflow,\n"
        "read:org, delete_repo scopes; or fine-grained with the access you want).\n"
    )
    return getpass.getpass("GitHub token (hidden): ").strip(), ""


def _github_connected_text(account: dict[str, Any], source: str) -> str:
    how = f" using {source}" if source else ""
    text = (
        f"Connected GitHub as {account.get('login')}{how}. The app, your agent's Manifest "
        "plugin and voice now use this connection too.\n"
    )
    scopes = account.get("scopes") or []
    if scopes and not {"repo", "workflow"} <= set(scopes):
        text += (
            f"Its scopes are {', '.join(scopes)}. For full control add repo and workflow "
            "(`gh auth refresh -s repo,workflow,delete_repo`), then connect again.\n"
        )
    return text


def _github_status_text(account: dict[str, Any]) -> str:
    text = f"{account.get('message')}\n"
    if account.get("connected") and account.get("scopes"):
        text += f"Scopes: {', '.join(account['scopes'])}\n"
    if not account.get("connected"):
        text += "Run `manifest github connect`.\n"
    return text


def _ask_yes(ctx: Context, question: str) -> bool:
    if not ctx.stdin.isatty():
        raise CliError("Add --yes to do this without a prompt.")
    ctx.err.write(f"{question} [y/N] ")
    ctx.err.flush()
    return ctx.stdin.readline().strip().lower() in {"y", "yes"}


def cmd_github(ctx: Context, argv: list[str]) -> int:
    parser = _sub(
        "github",
        BUILTINS["github"],
        epilog="connect links the GitHub login already on this computer (the GitHub CLI, or\n"
        "$GH_TOKEN / $GITHUB_TOKEN / $GITHUB_PERSONAL_ACCESS_TOKEN used by the GitHub plugin),\n"
        "otherwise asks for a token without showing it. It is checked with GitHub, stored\n"
        "encrypted in your account, and shared by the app, your agent's plugin and voice.\n"
        "Then every github-* command works: manifest github-repos · manifest github-issues\n"
        "--repo you/app · manifest github-create-pull-request --repo you/app --title ... --head\n"
        "feature. See them all with: manifest commands --search github",
    )
    parser.add_argument(
        "action", nargs="?", choices=["status", "connect", "disconnect"], default="status"
    )
    parser.add_argument(
        "--token-stdin", action="store_true", help="read the token from stdin (for scripts)"
    )
    parser.add_argument(
        "--no-gh",
        action="store_true",
        help="don't reuse a GitHub login found on this computer; ask for a token",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="don't ask before disconnecting")
    ns = parser.parse_args(argv)
    if not config.token(ns.token):
        raise CliError("Not signed in. Run `manifest login` first.")

    def run(document: str, variables: dict[str, Any] | None, field: str) -> dict[str, Any]:
        body = _run(_graphql(ctx, ns, document, variables))
        errors = body.get("errors") or []
        if errors:
            raise CliError("; ".join(str(e.get("message")) for e in errors))
        return (body.get("data") or {}).get(field) or {}

    fields = GITHUB_ACCOUNT_FIELDS
    if ns.action == "connect":
        token, source = _github_token(ctx, ns)
        if not token:
            raise CliError("No token given.")
        account = run(
            f"mutation ($token: String!) {{ connectGithub(token: $token) {{ {fields} }} }}",
            {"token": token},
            "connectGithub",
        )
        text = _github_connected_text(account, source)
    elif ns.action == "disconnect":
        if not ns.yes and not _ask_yes(ctx, "Disconnect GitHub from Manifest?"):
            ctx.err.write("Nothing changed.\n")
            return 1
        account = run(f"mutation {{ disconnectGithub {{ {fields} }} }}", None, "disconnectGithub")
        text = "GitHub is disconnected. Revoke the token on GitHub too if you no longer use it.\n"
    else:
        account = run(f"query {{ githubAccount {{ {fields} }} }}", None, "githubAccount")
        text = _github_status_text(account)
    if ns.json:
        output.emit(account, as_json=True, out=ctx.out)
    else:
        ctx.out.write(text)
    return 0


def cmd_bridge(ctx: Context, argv: list[str]) -> int:
    from manifest_cli import bridge
    from manifest_cli import bridge_setup as setup

    parser = _sub(
        "bridge",
        BUILTINS["bridge"],
        epilog="Keep it running, then use voice in the Manifest web app or the installed app:\n"
        "the browser listens and speaks, your agent answers. Only Manifest's own pages can\n"
        "reach it, on 127.0.0.1. Set up once with --install: it saves your agents and folders,\n"
        'answers with the agent you used last, and you can say "switch to Codex" any time.\n'
        "Example: manifest bridge --install --agent codex --workdir ~/Projects/myapp",
    )
    parser.add_argument(
        "--agent",
        default=None,
        metavar="AGENT",
        help="active (the agent you used last on this computer; default), claude, codex, "
        "or a command that reads the turn on stdin",
    )
    parser.add_argument(
        "--workdir",
        metavar="DIR",
        help="the project folder the agent works in (Codex needs a project it trusts: a Git "
        "repository; Claude Code's sessions are per folder)",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help="the agent's model for voice (default: a fast one, Claude Code's haiku; "
        "'default' keeps the agent's own setting)",
    )
    parser.add_argument(
        "--continue",
        dest="continue_last",
        action="store_true",
        help="continue the agent's newest session in its folder (incl. VS Code)",
    )
    parser.add_argument("--resume", metavar="SESSION", help="resume this agent session")
    parser.add_argument(
        "--agent-arg",
        action="append",
        default=None,
        metavar="ARG",
        help="extra argument for the agent, repeatable",
    )
    parser.add_argument("--port", type=int, default=None, help="local port (default 47821)")
    parser.add_argument(
        "--origin",
        action="append",
        default=None,
        metavar="URL",
        help="also allow this app origin (e.g. a self-hosted Manifest)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="save these settings, start the bridge at login and keep it running (macOS), "
        "then check that the agent can answer",
    )
    parser.add_argument("--uninstall", action="store_true", help="stop starting it at login")
    parser.add_argument(
        "--use",
        metavar="AGENT",
        help="switch the agent that answers: claude, codex, or active (the one you used last); "
        "the running bridge switches at once and remembers it",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="check everything voice needs (agents, folders, sign-in, bridge, Safari, voice) "
        "and say what to do next",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="with --doctor: also send each agent one short test turn",
    )
    parser.add_argument("--restart", action="store_true", help="restart the login item")
    parser.add_argument("--config", metavar="FILE", help=argparse.SUPPRESS)  # the login item
    parser.add_argument(
        "--check-voice",
        action="store_true",
        help="load the natural voice now (downloads it the first time) and say if it works",
    )
    parser.add_argument(
        "--cartesia-key",
        action="store_true",
        help="speak in Cartesia's voice (as in Pipecat's demos): asks for your Cartesia API key "
        "and keeps it in the macOS Keychain",
    )
    parser.add_argument(
        "--voice",
        metavar="NAME",
        help="Kokoro voice for natural local speech (default af_heart), or 'browser' for the browser's own voice",
    )
    ns = parser.parse_args(argv)
    if ns.uninstall:
        return bridge.uninstall(out=ctx.out)
    if ns.cartesia_key:
        return bridge.set_cartesia_key(out=ctx.out)
    if ns.check_voice:
        return bridge.check_voice(out=ctx.out)
    saved_path = Path(ns.config).expanduser() if ns.config else setup.settings_path()
    if ns.restart:
        current = setup.load(saved_path)
        return bridge.restart(out=ctx.out, port=current.port if current else bridge.DEFAULT_PORT)
    try:
        settings, explicit = _bridge_settings(ns, saved_path)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    if ns.use:
        return _bridge_use(ctx, settings, ns.use, saved_path)
    if ns.doctor:
        return _bridge_doctor(ctx, settings, run_probe=ns.probe)
    if ns.install:
        _ask_for_codex_folder(ctx, settings)
        if not settings.agents:
            raise CliError(
                "Manifest voice needs Claude Code or Codex on this computer first: "
                "https://claude.com/claude-code or https://developers.openai.com/codex"
            )
        try:
            setup.save(settings, saved_path)
        except (OSError, ValueError) as exc:
            raise CliError(f"Couldn't save the bridge settings: {exc}") from exc
        default = settings.agents.get(settings.default)
        return bridge.install(
            ["--config", str(saved_path)],
            out=ctx.out,
            workdir=default.folder if default else None,
            port=settings.port,
        )
    if not settings.agents:
        raise CliError("No agent found: install Claude Code or Codex, or pass --agent.")
    pool = bridge.AgentPool(settings, save_to=None if explicit else saved_path)
    return bridge.run(
        pool, port=settings.port, extra_origins=settings.origins, out=ctx.out, voice=settings.voice
    )


def _bridge_settings(ns: argparse.Namespace, saved_path: Path) -> tuple[Any, bool]:
    """The settings to use, and whether options on the command line changed them.

    One source of truth: the saved file (or, from an older install, the login item's own
    options), with this command's options on top. Without options the foreground bridge
    runs exactly what the login item runs."""
    from manifest_cli import bridge_setup as setup

    explicit = any(
        v is not None and v is not False
        for v in (
            ns.agent,
            ns.workdir,
            ns.model,
            ns.continue_last or None,
            ns.resume,
            ns.agent_arg,
            ns.port,
            ns.origin,
            ns.voice,
        )
    )
    saved = _saved_bridge_settings(saved_path, required=bool(ns.config))
    fresh = saved is None
    settings = saved or setup.BridgeSettings()
    if explicit and not (ns.install or ns.use or ns.doctor):
        settings = setup.BridgeSettings()  # a one-off foreground run: exactly these options
        fresh = True
    key = setup.agent_key(ns.agent) if ns.agent else settings.default
    if fresh or ns.install:
        for found in setup.installed_agents():  # every agent here, ready to switch to
            if key == setup.ACTIVE or not ns.agent or ns.install:
                settings.agents.setdefault(found, setup.AgentProfile())
    targets = list(settings.agents) if key == setup.ACTIVE else [key]
    for target in targets:
        _apply_agent_options(settings.profile(target), ns)
    codex = settings.agents.get("codex")
    if codex and not codex.workdir:
        codex.workdir = setup.suggested_folder("codex")
    settings.default = key
    if ns.port:
        settings.port = ns.port
    if ns.origin is not None:
        settings.origins = [o.rstrip("/") for o in ns.origin]
    if ns.voice:
        settings.voice = ns.voice
    settings.validate()
    return settings, explicit


def _saved_bridge_settings(saved_path: Path, *, required: bool) -> Any:
    from manifest_cli import bridge_setup as setup

    saved = setup.load(saved_path)
    if saved is None and required:
        raise ValueError(f"Can't read the bridge settings in {saved_path}.")
    if saved is None:
        old = setup.installed_args()
        if old and not setup.uses_saved_settings(old):
            saved = setup.settings_from_args(old)  # an older install: keep its choice
    return saved


def _apply_agent_options(profile: Any, ns: argparse.Namespace) -> None:
    if ns.workdir:
        profile.workdir = str(Path(ns.workdir).expanduser().resolve())
    if ns.model:
        profile.model = ns.model
    if ns.continue_last:
        profile.continue_last = True
    if ns.resume:
        profile.resume = ns.resume
    if ns.agent_arg is not None:
        profile.agent_args = list(ns.agent_arg)


def _ask_for_codex_folder(ctx: Context, settings: Any) -> None:
    """Codex answers only in a project it trusts: ask which one (never widen its trust)."""
    from manifest_cli import bridge_setup as setup

    codex = settings.agents.get("codex")
    if not codex or setup.codex_trusts(codex.folder):
        return
    interactive = hasattr(ctx.stdin, "isatty") and ctx.stdin.isatty()
    ctx.out.write(
        f"Codex only answers inside a project it trusts (a Git repository); {codex.folder} "
        "isn't one. Manifest won't change Codex's trust settings or bypass its check.\n"
    )
    if not interactive:
        ctx.out.write(
            'Choose one with: manifest bridge --install --agent codex --workdir "/path/to/project"\n'
        )
        return
    ctx.out.write("Which project folder should Codex work in? (Enter to set it up later) ")
    ctx.out.flush()
    answer = ctx.stdin.readline().strip()
    if not answer:
        return
    folder = Path(answer).expanduser().resolve()
    root = setup.git_root(folder) if folder.is_dir() else None
    if root is None:
        ctx.out.write(f"{folder} isn't a Git repository, so Codex won't run there; skipped.\n")
        return
    codex.workdir = str(root)
    ctx.out.write(f"Codex will work in {root}.\n")


def _bridge_use(ctx: Context, settings: Any, wanted: str, saved_path: Path) -> int:
    from manifest_cli import bridge_setup as setup

    key = setup.agent_key(wanted)
    if key != setup.ACTIVE:
        profile = settings.agents.get(key)
        if profile is None:
            profile = settings.profile(key)
            profile.workdir = setup.suggested_folder(key)
        problems = setup.check_agent(key, profile)
        if problems:
            for problem in problems:
                ctx.out.write(f"Not switched: {problem.message}\n  Next: {problem.fix}\n")
            return 1
    settings.default = key
    setup.save(settings, saved_path)
    told = setup.tell_bridge(settings.port, key)
    name = "the agent you use most recently" if key == setup.ACTIVE else setup.agent_name(key)
    if told and not told.get("error"):
        ctx.out.write(f"Voice now answers with {name} (now {told.get('agent')}); saved.\n")
    elif told and told.get("error"):
        ctx.out.write(f"Saved, but the bridge says: {told['error'].get('message')}\n")
        return 1
    else:
        ctx.out.write(f"Saved: voice answers with {name} when the bridge starts.\n")
    return 0


def _bridge_doctor(ctx: Context, settings: Any, *, run_probe: bool) -> int:
    from manifest_cli import bridge_setup as setup

    marks = {"ok": "✓", "warn": "!", "fail": "✗"}
    rows = setup.doctor(settings, run_probe=run_probe)
    for status, name, detail in rows:
        ctx.out.write(f"{marks[status]} {name}: {detail}\n")
    failed = any(status == "fail" for status, _, _ in rows)
    ctx.out.write("Something needs fixing (see ✗ above).\n" if failed else "Voice is ready.\n")
    return 1 if failed else 0


def cmd_completion(ctx: Context, argv: list[str]) -> int:
    from manifest_cli.completion import script

    parser = _sub("completion", BUILTINS["completion"])
    parser.add_argument("shell", choices=["zsh", "bash"])
    ns = parser.parse_args(argv)
    ctx.out.write(script(ns.shell))
    return 0


def cmd_complete(ctx: Context, argv: list[str]) -> int:
    """Hidden helper for completion scripts: options of one command."""
    from manifest_cli.completion import flags_for

    ctx.out.write("\n".join(flags_for(argv)) + "\n")
    return 0


# -- entry point ---------------------------------------------------------------


def dispatch(ctx: Context, argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        ctx.out.write(top_help())
        return 0
    if argv[0] in {"-V", "--version"}:
        ctx.out.write(f"manifest {__version__}\n")
        return 0
    name, rest_argv = argv[0], argv[1:]
    handlers = {
        "login": cmd_login,
        "logout": cmd_logout,
        "whoami": cmd_whoami,
        "voice": cmd_voice,
        "bridge": cmd_bridge,
        "vault-folder": cmd_vault_folder,
        "github": cmd_github,
        "commands": cmd_commands,
        "graphql": cmd_graphql,
        "api": cmd_api,
        "completion": cmd_completion,
        "__complete": cmd_complete,
    }
    if name in handlers:
        return handlers[name](ctx, rest_argv)
    if name in rest.groups():
        return cmd_rest_group(ctx, name, rest_argv)
    op = catalog.find(name)
    if op is not None:
        return cmd_operation(ctx, op, rest_argv)
    close = [o["command"] for o in catalog.operations() if name in o["command"]][:5]
    hint = f" Did you mean: {', '.join(close)}?" if close else " Run `manifest commands`."
    raise UsageError(f"unknown command {name!r}.{hint}")


def main(
    argv: list[str] | None = None,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    stdin: TextIO | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    open_url: Callable[[str], None] | None = None,
) -> int:
    ctx = Context(out or sys.stdout, err or sys.stderr, stdin or sys.stdin, transport, open_url)
    try:
        return dispatch(ctx, list(sys.argv[1:] if argv is None else argv))
    except UsageError as exc:
        ctx.err.write(f"manifest: {exc}\n")
        return 2
    except CliError as exc:
        ctx.err.write(f"manifest: {exc}\n")
        return 1
    except SystemExit as exc:  # argparse --help / usage errors
        return int(exc.code or 0) if isinstance(exc.code, int) else 2
    except KeyboardInterrupt:
        ctx.err.write("\n")
        return 130
    except Exception as exc:  # noqa: BLE001 - network failures etc.
        ctx.err.write(f"manifest: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
