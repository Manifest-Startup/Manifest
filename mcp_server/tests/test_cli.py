"""The `manifest` CLI: catalog-driven commands, flags, confirmation, auth and storage."""

from __future__ import annotations

import io
import json
import os
import stat
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from manifest_cli import auth, catalog, completion, config, main as cli, rest


class FakeStdin(io.StringIO):
    def __init__(self, text: str = "", tty: bool = False):
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class Backend:
    """httpx.MockTransport that records requests and answers GraphQL/REST."""

    def __init__(self, data: dict | None = None, status: int = 200):
        self.requests: list[httpx.Request] = []
        self.data = data if data is not None else {}
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/graphql":
            return httpx.Response(self.status, json={"data": self.data})
        return httpx.Response(self.status, json={"ok": True, "path": request.url.path})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def graphql_body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEST_CONFIG", str(tmp_path / "cfg" / "cli.json"))
    monkeypatch.delenv("MANIFEST_API_TOKEN", raising=False)
    monkeypatch.delenv("MANIFEST_API_URL", raising=False)
    return tmp_path / "cfg" / "cli.json"


def run(*argv: str, backend: Backend | None = None, stdin: FakeStdin | None = None):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        list(argv),
        out=out,
        err=err,
        stdin=stdin or FakeStdin(),
        transport=(backend or Backend()).transport,
    )
    return code, out.getvalue(), err.getvalue()


# -- catalog ---------------------------------------------------------------------


def test_catalog_covers_queries_and_mutations_with_unique_commands():
    ops = catalog.operations()
    kinds = {op["kind"] for op in ops}
    assert kinds == {"query", "mutation"}
    commands = [op["command"] for op in ops]
    assert len(commands) == len(set(commands))
    reserved = set(cli.BUILTINS) | set(rest.groups()) | {"__complete"}
    assert not reserved & set(commands)
    assert all(c == c.lower() and "_" not in c for c in commands)


def test_destructive_mutations_are_flagged():
    flagged = {op["command"] for op in catalog.operations() if op["destructive"]}
    assert {"delete-idea", "revoke-account-session", "create-investment", "remove-collaborator"} <= flagged
    assert "create-idea" not in flagged
    assert not any(op["destructive"] for op in catalog.operations() if op["kind"] == "query")


def test_document_from_flags():
    op = catalog.find("create-idea")
    parser = cli.operation_parser(op)
    ns = parser.parse_args(["--title", "Robots", "--description", "for lawns"])
    variables = catalog.variables_from_args(op, ns)
    assert variables == {"title": "Robots", "description": "for lawns"}
    document = catalog.build_document(op, variables)
    assert document.startswith("mutation CreateIdea($title: String!, $description: String)")
    assert "createIdea(title: $title, description: $description) {" in document


def test_select_overrides_default_fields():
    op = catalog.find("create-idea")
    assert catalog.build_document(op, {"title": "x"}, "ideaId title").endswith(
        "createIdea(title: $title) { ideaId title } }"
    )


def test_required_flags_are_enforced():
    code, _, err = run("create-idea")
    assert code == 2 and "--title" in err


def test_typed_scalars_are_converted_and_validated():
    op = next(
        o
        for o in catalog.operations()
        if any(a["type"].startswith("Int") for a in o["args"])
    )
    arg = next(a for a in op["args"] if a["type"].startswith("Int"))
    assert catalog.convert("5", arg["type"], what=arg["flag"]) == 5
    with pytest.raises(catalog.UsageError):
        catalog.convert("five", arg["type"], what=arg["flag"])
    assert catalog.convert("yes", "Boolean", what="--x") is True


def test_input_objects_from_json_file_stdin_and_field_flags(tmp_path, monkeypatch):
    op = catalog.find("update-account")
    parser = cli.operation_parser(op)
    payload = tmp_path / "account.json"
    payload.write_text(json.dumps({"bio": "hi", "firstName": "A"}))
    ns = parser.parse_args(["--input", f"@{payload}", "--first-name", "Ada"])
    assert catalog.variables_from_args(op, ns) == {"input": {"bio": "hi", "firstName": "Ada"}}

    monkeypatch.setattr("sys.stdin", io.StringIO('{"country": "IN"}'))
    ns = parser.parse_args(["--input", "-"])
    assert catalog.variables_from_args(op, ns) == {"input": {"country": "IN"}}

    ns = parser.parse_args(["--skills", "python", "--skills", "go"])
    assert catalog.variables_from_args(op, ns) == {"input": {"skills": ["python", "go"]}}

    with pytest.raises(catalog.UsageError):
        catalog.variables_from_args(op, parser.parse_args(["--input", "{not json"]))


def test_help_comes_from_the_catalog(capsys):
    code, _, _ = run("delete-idea", "--help")
    text = capsys.readouterr().out
    assert code == 0
    assert "Delete an idea owned by the current user." in text
    assert "--idea-id" in text and "--yes" in text and "confirmation" in text


def test_commands_lists_and_searches():
    code, out, _ = run("commands")
    assert code == 0
    total = len(catalog.operations()) + len(rest.REST_COMMANDS) + len(cli.BUILTINS)
    assert f"{total} commands" in out
    code, out, _ = run("commands", "--search", "collaborator", "--json")
    rows = json.loads(out)
    assert rows and all("collaborator" in r["command"] or "collaborator" in r["description"].lower() for r in rows)


def test_unknown_command_suggests():
    code, _, err = run("idea-version")
    assert code == 2 and "idea-versions" in err


# -- running ---------------------------------------------------------------------


def test_runs_with_bearer_token_and_prints_readable_output():
    config.save({"base_url": "https://manifest.test", "token": "tok-123"})
    backend = Backend({"ideas": [{"ideaId": "i1", "title": "Robots"}]})
    code, out, err = run("ideas", backend=backend)
    assert code == 0, err
    request = backend.requests[0]
    assert str(request.url) == "https://manifest.test/graphql"
    assert request.headers["authorization"] == "Bearer tok-123"
    assert request.headers["user-agent"].startswith("manifest-cli/")
    assert "ideaId" in out and "Robots" in out and "{" not in out

    code, out, _ = run("ideas", "--json", backend=backend)
    assert json.loads(out) == [{"ideaId": "i1", "title": "Robots"}]


def test_env_overrides_saved_login(monkeypatch):
    config.save({"base_url": "https://saved.test", "token": "saved"})
    monkeypatch.setenv("MANIFEST_API_URL", "https://env.test")
    monkeypatch.setenv("MANIFEST_API_TOKEN", "env-token")
    backend = Backend({"ideas": []})
    run("ideas", backend=backend)
    assert backend.requests[0].url.host == "env.test"
    assert backend.requests[0].headers["authorization"] == "Bearer env-token"


def test_graphql_errors_exit_nonzero():
    def handler(request):
        return httpx.Response(200, json={"data": None, "errors": [{"message": "Missing token"}]})

    out, err = io.StringIO(), io.StringIO()
    code = cli.main(["ideas"], out=out, err=err, stdin=FakeStdin(), transport=httpx.MockTransport(handler))
    assert code == 1 and "Missing token" in err.getvalue() and "manifest login" in err.getvalue()


@pytest.mark.parametrize("answer, expected_requests", [("y\n", 1), ("n\n", 0)])
def test_destructive_commands_prompt_on_a_tty(answer, expected_requests):
    backend = Backend({"deleteIdea": True})
    code, _, err = run("delete-idea", "--idea-id", "i1", backend=backend, stdin=FakeStdin(answer, tty=True))
    assert len(backend.requests) == expected_requests
    assert "Continue?" in err
    assert code == (0 if expected_requests else 1)


def test_destructive_commands_need_yes_when_not_interactive():
    backend = Backend({"deleteIdea": True})
    code, _, err = run("delete-idea", "--idea-id", "i1", backend=backend)
    assert code == 2 and "--yes" in err and not backend.requests
    code, _, _ = run("delete-idea", "--idea-id", "i1", "--yes", backend=backend)
    assert code == 0 and len(backend.requests) == 1


def test_graphql_escape_hatch():
    backend = Backend({"me": {"userId": "u1"}})
    code, out, _ = run("graphql", "query { me { userId } }", "--variables", '{"a": 1}', "--json", backend=backend)
    assert code == 0 and json.loads(out) == {"me": {"userId": "u1"}}
    assert backend.graphql_body() == {"query": "query { me { userId } }", "variables": {"a": 1}}


def test_api_escape_hatch_and_delete_confirmation():
    backend = Backend()
    code, out, _ = run("api", "get", "/api/keys/usage", "-q", "days=7", "--json", backend=backend)
    assert code == 0 and json.loads(out)["path"] == "/api/keys/usage"
    assert backend.requests[0].url.params["days"] == "7"
    code, _, err = run("api", "DELETE", "/api/keys/keys/k1", backend=backend)
    assert code == 2 and len(backend.requests) == 1


def test_rest_commands_build_paths_and_bodies():
    backend = Backend()
    code, _, err = run("keys", "create", "--client-id", "c1", "--scopes", "ideas:read", "--expires-days", "30", backend=backend)
    assert code == 0, err
    request = backend.requests[-1]
    assert request.method == "POST" and request.url.path == "/api/keys/keys"
    assert json.loads(request.content) == {"client_id": "c1", "scopes": ["ideas:read"], "expires_days": 30}

    code, _, _ = run("keys", "revoke", "k/1", "--yes", backend=backend)
    assert code == 0 and backend.requests[-1].method == "DELETE"
    assert backend.requests[-1].url.raw_path == b"/api/keys/keys/k%2F1"

    code, _, _ = run("privacy", "set-consent", "--analytics-enabled", "false", backend=backend)
    assert json.loads(backend.requests[-1].content) == {"analytics_enabled": False}


def test_rest_http_errors_are_explained():
    backend = Backend(status=401)
    code, _, err = run("keys", "clients", backend=backend)
    assert code == 1 and "HTTP 401" in err and "manifest login" in err


def test_upload_profile_picture_sends_multipart(tmp_path):
    picture = tmp_path / "me.png"
    picture.write_bytes(b"\x89PNG fake")
    backend = Backend()
    code, _, err = run("upload-profile-picture", str(picture), backend=backend)
    assert code == 0, err
    request = backend.requests[-1]
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'filename="me.png"' in request.content


# -- auth & storage ----------------------------------------------------------------


def test_config_is_private(isolated_config):
    path = config.save({"token": "secret", "base_url": "https://x.test"})
    assert path == isolated_config
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    assert config.load()["token"] == "secret"


def test_pkce_pair_is_s256():
    import base64
    import hashlib

    pkce = auth.new_pkce()
    assert 43 <= len(pkce.verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(pkce.verifier.encode()).digest()).rstrip(b"=").decode()
    assert pkce.challenge == expected


def _callback_opener(**params):
    def open_url(url: str) -> None:
        query = parse_qs(urlsplit(url).query)
        redirect = query["redirect_uri"][0]
        assert redirect.startswith("http://127.0.0.1:") and redirect.endswith("/callback")
        assert query["code_challenge_method"] == ["S256"]
        values = {"state": query["state"][0], **params}
        httpx.get(redirect, params={k: v for k, v in values.items() if v is not None}, timeout=5)

    return open_url


def test_loopback_callback_returns_the_code():
    pkce = auth.new_pkce()
    code, redirect = auth.wait_for_callback(pkce, _callback_opener(code="abc"), base_url="https://m.test", timeout=5)
    assert code == "abc" and redirect.startswith("http://127.0.0.1:")


def test_loopback_callback_rejects_a_different_state():
    with pytest.raises(auth.LoginError, match="state"):
        auth.wait_for_callback(
            auth.new_pkce(), _callback_opener(code="abc", state="forged-state"), base_url="https://m.test", timeout=5
        )


def test_loopback_callback_reports_cancel():
    with pytest.raises(auth.LoginError, match="cancelled"):
        auth.wait_for_callback(
            auth.new_pkce(), _callback_opener(error="access_denied"), base_url="https://m.test", timeout=5
        )


def test_login_saves_the_session(isolated_config):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/cli/token"
        assert body["code"] == "abc" and len(body["code_verifier"]) >= 43 and body["hostname"]
        return httpx.Response(
            200,
            json={
                "access_token": "cli-token",
                "token_type": "Bearer",
                "expires_at": "2026-12-15T00:00:00+00:00",
                "label": "Manifest CLI · box",
                "user": {"user_id": "u1", "email": "ada@example.com"},
            },
        )

    err = io.StringIO()
    code = cli.main(
        ["login", "--base-url", "https://m.test", "--timeout", "5"],
        out=io.StringIO(),
        err=err,
        stdin=FakeStdin(),
        transport=httpx.MockTransport(handler),
        open_url=_callback_opener(code="abc"),
    )
    assert code == 0, err.getvalue()
    saved = json.loads(isolated_config.read_text())
    assert saved["token"] == "cli-token" and saved["base_url"] == "https://m.test"
    assert stat.S_IMODE(os.stat(isolated_config).st_mode) == 0o600


def test_logout_revokes_and_forgets():
    config.save({"base_url": "https://m.test", "token": "cli-token", "label": "Manifest CLI · box"})
    backend = Backend()
    code, _, err = run("logout", backend=backend)
    assert code == 0 and "revoked" in err
    request = backend.requests[0]
    assert request.url.path == "/api/auth/logout" and request.headers["authorization"] == "Bearer cli-token"
    assert config.load() == {"base_url": "https://m.test"}


def test_whoami_requires_login():
    code, _, err = run("whoami")
    assert code == 1 and "manifest login" in err


# -- completion --------------------------------------------------------------------


@pytest.mark.parametrize("shell", ["zsh", "bash"])
def test_completion_scripts(shell):
    code, out, _ = run("completion", shell)
    assert code == 0 and "create-idea" in out and "manifest __complete" in out


def test_completion_flags():
    assert "--title" in completion.flags_for(["create-idea"])
    assert "create" in completion.flags_for(["keys"])
    assert "--client-id" in completion.flags_for(["keys", "create"])
