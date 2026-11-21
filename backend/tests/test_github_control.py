"""Connecting your own GitHub and controlling it (github_account, github_api, github* GraphQL)."""

from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from app.services.integrations import connections, github_account
from app.services.integrations import github_api as gh
from app.services.integrations.github_api import GitHubClient, GitHubError

TOKEN = "ghp_" + "a" * 36


class FakeGitHub:
    """Records requests and answers from a {(method, path): response} table."""

    def __init__(self, routes: dict[tuple[str, str], tuple[int, object]]):
        self.routes = routes
        self.calls: list[tuple[str, str, dict, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, dict(request.url.params), body))
        status, payload = self.routes.get(
            (request.method, request.url.path), (404, {"message": "Not Found"})
        )
        headers = {"x-oauth-scopes": "repo, workflow"} if request.url.path == "/user" else {}
        return httpx.Response(status, json=payload, headers=headers)

    def client(self) -> GitHubClient:
        return GitHubClient(TOKEN, transport=httpx.MockTransport(self))


# --------------------------------------------------------------------------- input checks


def test_repo_accepts_owner_name_and_urls():
    assert gh.check_repo("octo/hello") == "octo/hello"
    assert gh.check_repo("https://github.com/octo/hello.git") == "octo/hello"
    for bad in ("", "octo", "octo/hello/extra", "../x", "octo/he llo"):
        with pytest.raises(GitHubError):
            gh.check_repo(bad)


@pytest.mark.parametrize(
    "bad", ["https://evil.example/x", "//evil.example", "/repos/../user", "repos/x", "/a b"]
)
def test_raw_api_paths_stay_on_api_github_com(bad):
    with pytest.raises(GitHubError):
        gh.check_api_path(bad)
    assert gh.check_api_path("https://api.github.com/user") == "/user"


@pytest.mark.parametrize("bad", ["../secret", "a/../b", "a//b", "a\\b"])
def test_file_paths_cannot_escape(bad):
    with pytest.raises(GitHubError):
        gh.check_path(bad)


def test_clean_token_rejects_junk_and_strips_bearer():
    assert github_account.clean_token(f"Bearer {TOKEN} ") == TOKEN
    for bad in ("", "***", "short", "has space " + "x" * 30):
        with pytest.raises(github_account.GitHubConnectError):
            github_account.clean_token(bad)


# --------------------------------------------------------------------------- account


def test_verify_token_reads_login_and_scopes():
    fake = FakeGitHub(
        {
            ("GET", "/user"): (
                200,
                {"login": "octo", "name": "Octo Cat", "html_url": "https://github.com/octo"},
            )
        }
    )
    identity = github_account.verify_token(
        TOKEN, method="oauth", transport=httpx.MockTransport(fake)
    )
    assert identity.login == "octo"
    assert identity.scopes == ["repo", "workflow"]
    assert identity.method == "oauth"
    assert github_account.GitHubIdentity.from_metadata(identity.to_metadata()) == identity


def test_verify_token_rejection_is_a_clear_error():
    fake = FakeGitHub({("GET", "/user"): (401, {"message": "Bad credentials"})})
    with pytest.raises(github_account.GitHubConnectError, match="rejected"):
        github_account.verify_token(TOKEN, transport=httpx.MockTransport(fake))


class _FakeCursor:
    """Just enough of a psycopg cursor for github_account's four statements."""

    def __init__(self, stored: dict[str, object]):
        self.stored, self.row = stored, None

    def execute(self, sql: str, params: tuple) -> None:
        verb = sql.strip().split()[0]
        if verb == "INSERT":
            self.stored.update(
                user_id=params[0],
                service_id=params[1],
                access_token=None,
                access_token_ciphertext=params[3],
                refresh_token=None,
                refresh_token_ciphertext=None,
                metadata=params[5],
            )
        elif verb == "DELETE":
            self.stored.clear()
        elif "FROM users" in sql:
            self.row = {"data_region": None}
        else:
            self.row = dict(self.stored) if self.stored else None

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, stored: dict[str, object]):
        self.stored = stored

    def cursor(self):
        return _FakeCursor(self.stored)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_token_is_stored_encrypted_and_read_back(monkeypatch):
    """save → load round-trips through the real AES-GCM envelope; plaintext column stays NULL."""
    stored: dict[str, object] = {}
    monkeypatch.setattr(github_account, "get_db_connection", lambda: _FakeConn(stored))
    monkeypatch.setattr(
        github_account,
        "verify_token",
        lambda token, method="token", transport=None: github_account.GitHubIdentity(
            login="octo", method=method
        ),
    )
    dek = b"k" * 32
    monkeypatch.setattr(github_account, "get_or_create_tenant_dek", lambda kind, uid: dek)
    monkeypatch.setattr(
        "app.services.integrations.token_crypto.get_or_create_tenant_dek", lambda kind, uid: dek
    )
    monkeypatch.setattr(github_account, "get_active_kek_version", lambda: 1)

    identity = github_account.save_github_token("user-1", TOKEN)
    assert identity.login == "octo"
    assert stored["access_token"] is None
    assert TOKEN.encode() not in bytes(stored["access_token_ciphertext"])  # type: ignore[arg-type]
    assert github_account.load_github_token("user-1") == TOKEN
    assert github_account.github_identity("user-1").login == "octo"  # type: ignore[union-attr]
    github_account.disconnect_github("user-1")
    assert github_account.load_github_token("user-1") is None
    assert github_account.github_identity("user-1") is None


def test_github_is_never_recorded_without_a_token(monkeypatch):
    monkeypatch.setattr(github_account, "github_identity", lambda uid: None)
    db = SimpleNamespace(table=lambda name: pytest.fail("must not write a token-less GitHub row"))
    result = connections.start_connection(
        db, "u1", "GitHub", oauth_ready=False, site_origin="https://m.test"
    )
    assert result.status == connections.STATUS_NEEDS_BROWSER
    assert result.connect_url == "https://m.test/account?focusIntegration=github"
    assert "manifest github connect" in result.message


# --------------------------------------------------------------------------- operations


def test_list_repos_and_issues_drop_pull_requests():
    fake = FakeGitHub(
        {
            ("GET", "/user/repos"): (
                200,
                [
                    {
                        "full_name": "octo/app",
                        "name": "app",
                        "owner": {"login": "octo"},
                        "private": True,
                        "html_url": "u",
                    }
                ],
            ),
            ("GET", "/repos/octo/app/issues"): (
                200,
                [{"number": 1, "title": "Bug"}, {"number": 2, "title": "PR", "pull_request": {}}],
            ),
        }
    )
    with fake.client() as client:
        repos = gh.list_repos(client, limit=500)
        issues = gh.list_issues(client, "octo/app", state="all")
    assert repos[0]["full_name"] == "octo/app" and repos[0]["private"] is True
    assert fake.calls[0][2]["per_page"] == "100"  # clamped
    assert [i["number"] for i in issues] == [1]
    assert fake.calls[1][2]["state"] == "all"


def test_put_file_updates_with_existing_sha_and_creates_without():
    content_path = "/repos/octo/app/contents/docs/plan.md"
    fake = FakeGitHub(
        {
            ("GET", content_path): (200, {"sha": "old-sha", "type": "file"}),
            ("PUT", content_path): (
                200,
                {"commit": {"sha": "new-sha"}, "content": {"html_url": "h"}},
            ),
        }
    )
    with fake.client() as client:
        result = gh.put_file(
            client, "octo/app", path="docs/plan.md", content="hello", branch="main"
        )
    put = fake.calls[-1]
    assert put[3]["sha"] == "old-sha" and put[3]["branch"] == "main"
    assert base64.b64decode(put[3]["content"]).decode() == "hello"
    assert result == {
        "path": "docs/plan.md",
        "commit_sha": "new-sha",
        "html_url": "h",
        "created": False,
    }

    fake.routes[("GET", content_path)] = (404, {"message": "Not Found"})
    with fake.client() as client:
        assert gh.put_file(client, "octo/app", path="docs/plan.md", content="x")["created"] is True
    assert "sha" not in fake.calls[-1][3]
    assert fake.calls[-1][3]["message"] == "Add docs/plan.md"


def test_get_contents_decodes_text_and_lists_folders():
    text = base64.b64encode(b"# Hi").decode()
    fake = FakeGitHub(
        {
            ("GET", "/repos/octo/app/contents/README.md"): (
                200,
                {
                    "type": "file",
                    "path": "README.md",
                    "size": 4,
                    "encoding": "base64",
                    "content": text,
                },
            ),
            ("GET", "/repos/octo/app/contents/"): (
                200,
                [{"name": "src", "path": "src", "type": "dir"}],
            ),
        }
    )
    with fake.client() as client:
        assert gh.get_contents(client, "octo/app", path="README.md")["text"] == "# Hi"
        folder = gh.get_contents(client, "octo/app")
    assert folder["type"] == "dir" and folder["entries"][0]["name"] == "src"


def test_create_branch_from_default_branch():
    fake = FakeGitHub(
        {
            ("GET", "/repos/octo/app"): (200, {"default_branch": "main"}),
            ("GET", "/repos/octo/app/commits/main"): (200, {"sha": "abc"}),
            ("POST", "/repos/octo/app/git/refs"): (201, {}),
        }
    )
    with fake.client() as client:
        assert gh.create_branch(client, "octo/app", "feature/x") == {
            "name": "feature/x",
            "sha": "abc",
            "protected": False,
        }
    assert fake.calls[-1][3] == {"ref": "refs/heads/feature/x", "sha": "abc"}


def test_merge_pull_and_review():
    fake = FakeGitHub(
        {
            ("PUT", "/repos/octo/app/pulls/7/merge"): (200, {"merged": True}),
            ("GET", "/repos/octo/app/pulls/7"): (
                200,
                {
                    "number": 7,
                    "state": "closed",
                    "merged_at": "now",
                    "head": {"ref": "f"},
                    "base": {"ref": "main"},
                },
            ),
            ("POST", "/repos/octo/app/pulls/7/reviews"): (200, {}),
        }
    )
    with fake.client() as client:
        pull = gh.merge_pull(client, "octo/app", 7)
        assert gh.review_pull(client, "octo/app", 7, event="approve")
        with pytest.raises(GitHubError):
            gh.merge_pull(client, "octo/app", 7, method="octopus")
        with pytest.raises(GitHubError, match="review comment"):
            gh.review_pull(client, "octo/app", 7, event="REQUEST_CHANGES")
    assert pull["state"] == "merged" and pull["merged"] is True
    assert fake.calls[0][3] == {"merge_method": "squash"}


def test_run_workflow_sends_inputs_as_strings():
    fake = FakeGitHub(
        {
            ("GET", "/repos/octo/app"): (200, {"default_branch": "main"}),
            ("POST", "/repos/octo/app/actions/workflows/deploy.yml/dispatches"): (204, None),
        }
    )
    with fake.client() as client:
        assert gh.run_workflow(
            client, "octo/app", workflow="deploy.yml", inputs='{"env": "prod", "n": 2}'
        )
        with pytest.raises(GitHubError, match="JSON"):
            gh.run_workflow(client, "octo/app", workflow="deploy.yml", inputs="{nope")
    assert fake.calls[1][3] == {"ref": "main", "inputs": {"env": "prod", "n": "2"}}


def test_api_request_passes_status_through():
    fake = FakeGitHub({("GET", "/notifications"): (200, [{"id": "1"}])})
    with fake.client() as client:
        ok = gh.api_request(client, method="get", path="/notifications")
        missing = gh.api_request(client, method="DELETE", path="/repos/octo/app/labels/x")
        with pytest.raises(GitHubError):
            gh.api_request(client, method="TRACE", path="/user")
    assert ok["status"] == 200 and json.loads(ok["body"]) == [{"id": "1"}]
    assert missing["status"] == 404 and missing["ok"] is False


@pytest.mark.parametrize(
    ("status", "headers", "needle"),
    [
        (401, {}, "Reconnect GitHub"),
        (403, {"x-ratelimit-remaining": "0"}, "rate limit"),
        (404, {}, "doesn't exist"),
        (422, {}, "name already exists"),
    ],
)
def test_github_errors_are_actionable(status, headers, needle):
    def handler(request):
        return httpx.Response(
            status,
            json={
                "message": "Validation Failed",
                "errors": [{"message": "name already exists on this account"}],
            },
            headers=headers,
        )

    with GitHubClient(TOKEN, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GitHubError, match=needle):
            gh.get_repo(client, "octo/app")


def test_not_connected_says_how_to_connect(monkeypatch):
    monkeypatch.setattr(gh, "load_github_token", lambda uid: None)
    with pytest.raises(GitHubError, match="manifest github connect"):
        gh.client_for("user-1")


# --------------------------------------------------------------------------- GraphQL


def _execute(document: str, variables: dict | None = None):
    from app.graphql.schema import schema

    request = SimpleNamespace(
        state=SimpleNamespace(), headers={}, cookies={}, scope={}, client=None
    )
    return asyncio.run(
        schema.execute(
            document, variable_values=variables, context_value={"request": request, "db": None}
        )
    )


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(
        "app.graphql.resolvers.github.get_current_user_id", lambda request: "user-1"
    )
    monkeypatch.setattr(
        "app.graphql.schema.get_current_user_id_optional", lambda request: "user-1", raising=False
    )
    monkeypatch.setattr(
        "app.graphql.schema.get_current_user_id", lambda request: "user-1", raising=False
    )
    monkeypatch.setattr(
        "app.graphql.schema.resolve_principal",
        lambda *a, **k: SimpleNamespace(
            user_id="user-1", is_guest=False, role="user", has=lambda permission: True
        ),
        raising=False,
    )


def test_graphql_account_when_not_connected(signed_in, monkeypatch):
    monkeypatch.setattr("app.graphql.resolvers.github.github_identity", lambda uid: None)
    result = _execute("{ githubAccount { connected oauthAvailable connectUrl message } }")
    assert result.errors is None, result.errors
    account = result.data["githubAccount"]
    assert account["connected"] is False
    assert account["connectUrl"].endswith("/account?focusIntegration=github")
    assert "manifest github connect" in account["message"]


def test_graphql_create_issue_through_the_person_s_client(signed_in, monkeypatch):
    fake = FakeGitHub(
        {
            ("POST", "/repos/octo/app/issues"): (
                201,
                {
                    "number": 9,
                    "title": "Ship it",
                    "state": "open",
                    "html_url": "h",
                    "labels": [{"name": "launch"}],
                },
            )
        }
    )
    monkeypatch.setattr(gh, "client_for", lambda uid: fake.client())
    result = _execute(
        'mutation { githubCreateIssue(repo: "octo/app", title: "Ship it", labels: ["launch"]) { number labels htmlUrl } }'
    )
    assert result.errors is None, result.errors
    assert result.data["githubCreateIssue"] == {"number": 9, "labels": ["launch"], "htmlUrl": "h"}
    assert fake.calls[0][3] == {"title": "Ship it", "labels": ["launch"]}


def test_graphql_github_errors_reach_the_client(signed_in, monkeypatch):
    monkeypatch.setattr(gh, "load_github_token", lambda uid: None)
    result = _execute("{ githubRepos { fullName } }")
    assert result.errors and "manifest github connect" in result.errors[0].message


def test_risky_github_commands_ask_first():
    from pathlib import Path

    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2] / "mcp_server/src/manifest_cli/catalog.json"
        ).read_text()
    )
    ops = {op["name"]: op for op in catalog["operations"]}
    for name in (
        "githubDeleteRepo",
        "githubDeleteBranch",
        "githubDeleteFile",
        "githubMergePullRequest",
        "githubUpdateRepo",
        "githubApiRequest",
        "disconnectGithub",
    ):
        assert ops[name]["destructive"], name
    for name in ("githubRepos", "githubCreateIssue", "githubComment", "githubApi"):
        assert not ops[name]["destructive"], name
