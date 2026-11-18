"""End to end: the real ``manifest`` CLI against the real FastAPI app (in-process).

``manifest login`` runs its loopback server on 127.0.0.1, the "browser" (a TestClient
with a signed-in session cookie) approves it, and later commands reach GraphQL and
REST through ``httpx.ASGITransport`` with the CLI's bearer token.
"""

from __future__ import annotations

import io
import json
import os
import stat
from urllib.parse import urlsplit

import httpx
import pytest
from app.auth import current_user
from cli_fakes import sessions  # noqa: F401 - pytest fixture
from fastapi.testclient import TestClient

manifest_cli_main = pytest.importorskip("manifest_cli.main")


class NotATty(io.StringIO):
    def isatty(self) -> bool:
        return False


@pytest.fixture
def app(monkeypatch, sessions):  # noqa: F811
    from app.graphql.resolvers import account as account_resolvers
    from app.main import app as fastapi_app

    def list_sessions(user_id, current_sid):
        return [
            {
                "session_id": sid,
                "user_agent": row["user_agent"],
                "kind": "cli" if str(row["user_agent"]).startswith("Manifest CLI · ") else "browser",
                "current": sid == current_sid,
            }
            for sid, row in sessions.rows.items()
            if row["user_id"] == user_id and not row["revoked"]
        ]

    monkeypatch.setattr(account_resolvers, "list_user_sessions", list_sessions)
    return fastapi_app


@pytest.fixture
def cli(app, tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEST_CONFIG", str(tmp_path / "manifest" / "cli.json"))
    monkeypatch.delenv("MANIFEST_API_TOKEN", raising=False)
    monkeypatch.delenv("MANIFEST_API_URL", raising=False)

    browser = TestClient(app, base_url="http://testserver", follow_redirects=False)
    browser.cookies.set("session_token", current_user.create_session_token("u1", "ada@example.com"))

    def approve_in_browser(url: str) -> None:
        parts = urlsplit(url)
        page = browser.get(f"{parts.path}?{parts.query}")
        assert page.status_code == 200, page.text
        href = page.text.split('data-testid="cli-allow" href="')[1].split('"')[0]
        allowed = browser.get(href.replace("&amp;", "&"))
        assert allowed.status_code == 303
        # The browser follows the redirect to the CLI's loopback server.
        httpx.get(allowed.headers["location"], timeout=5)

    def run(*argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = manifest_cli_main.main(
            list(argv),
            out=out,
            err=err,
            stdin=NotATty(""),
            transport=httpx.ASGITransport(app=app),
            open_url=approve_in_browser,
        )
        return code, out.getvalue(), err.getvalue()

    return run


def test_login_use_and_logout(cli, tmp_path, sessions):  # noqa: F811
    code, _, err = cli("login", "--base-url", "http://testserver", "--timeout", "10")
    assert code == 0, err
    assert "Signed in to http://testserver as ada@example.com" in err

    stored = tmp_path / "manifest" / "cli.json"
    assert stat.S_IMODE(os.stat(stored).st_mode) == 0o600
    saved = json.loads(stored.read_text())
    assert saved["base_url"] == "http://testserver"
    assert saved["label"].startswith("Manifest CLI · ")

    # A generated GraphQL command, with the bearer token.
    code, out, err = cli("my-sessions", "--json")
    assert code == 0, err
    listed = json.loads(out)
    cli_rows = [row for row in listed if row["kind"] == "cli"]
    assert len(cli_rows) == 1 and cli_rows[0]["current"] is True

    # The raw escape hatch.
    code, out, err = cli("graphql", "{ mySessions { kind } }", "--json")
    assert code == 0, err
    assert {"kind": "cli"} in json.loads(out)["mySessions"]

    # Destructive mutations refuse to run unattended without --yes.
    code, _, err = cli("delete-idea", "--idea-id", "i1")
    assert code == 2 and "--yes" in err

    # Logout revokes the CLI session server-side and forgets it locally.
    code, _, err = cli("logout")
    assert code == 0 and "revoked" in err
    assert all(row["revoked"] for row in sessions.rows.values() if str(row["user_agent"] or "").startswith("Manifest CLI"))
    assert "token" not in json.loads(stored.read_text())

    code, _, err = cli("whoami")
    assert code == 1 and "manifest login" in err
