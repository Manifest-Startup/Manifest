"""Manifest CLI sign-in (ADR 0003): /api/cli/authorize and /api/cli/token.

PKCE, loopback-only redirects, state, one-time codes, expiry, guests, revocation.
"""

from __future__ import annotations

import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from app.auth import current_user
from app.auth.current_user import require_user_id
from app.routes import auth_routes, cli_auth_routes
from app.services.identity import cli_auth, sessions as sessions_service
from cli_fakes import pkce_pair, sessions  # noqa: F401 - pytest fixture
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

LOOPBACK = "http://127.0.0.1:53682/callback"
STATE = "state-1234567890"


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(cli_auth_routes.router)
    application.include_router(auth_routes.router)

    @application.get("/whoami")
    def whoami(user_id: str = Depends(require_user_id)):
        return {"user_id": user_id}

    return application


@pytest.fixture
def browser(app, sessions, monkeypatch):  # noqa: F811
    """A browser for user u1 that signed in just now (not demo mode)."""
    monkeypatch.setattr(cli_auth_routes, "DEMO_MODE", False)
    client = TestClient(app, follow_redirects=False)
    token = current_user.create_session_token("u1", "ada@example.com")
    client.cookies.set("session_token", token)
    return client


def authorize_params(challenge: str, **overrides) -> dict:
    params = {
        "redirect_uri": LOOPBACK,
        "state": STATE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return {k: v for k, v in params.items() if v is not None}


def approve(client: TestClient, challenge: str, redirect_uri: str = LOOPBACK) -> str:
    """Open the confirm page, follow Allow, return the one-time code."""
    page = client.get("/api/cli/authorize", params=authorize_params(challenge, redirect_uri=redirect_uri))
    assert page.status_code == 200, page.text
    href = page.text.split('data-testid="cli-allow" href="')[1].split('"')[0].replace("&amp;", "&")
    allowed = client.get(href)
    assert allowed.status_code == 303
    target = urlsplit(allowed.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == redirect_uri
    query = parse_qs(target.query)
    assert query["state"] == [STATE]
    return query["code"][0]


def exchange(client: TestClient, code: str, verifier: str, **extra):
    body = {"code": code, "code_verifier": verifier, "redirect_uri": LOOPBACK, "hostname": "ada-mbp"}
    body.update(extra)
    return client.post("/api/cli/token", json=body)


# -- authorize -------------------------------------------------------------


def test_signed_out_browser_goes_through_open_media_login(app, sessions):  # noqa: F811
    _, challenge = pkce_pair()
    response = TestClient(app, follow_redirects=False).get(
        "/api/cli/authorize", params=authorize_params(challenge)
    )
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/login"
    next_path = parse_qs(location.query)["next"][0]
    assert next_path.startswith("/api/cli/authorize?")
    # The login page hands `next` to Open Media sign-in, which must allow it back.
    assert auth_routes.safe_next(next_path) == next_path
    assert auth_routes.safe_next("/api/keys/clients") == "/ideas"


def test_guests_must_sign_in_first(browser, sessions):  # noqa: F811
    sessions.guests.add("u1")
    _, challenge = pkce_pair()
    response = browser.get("/api/cli/authorize", params=authorize_params(challenge))
    assert response.status_code == 303 and response.headers["location"].startswith("/login?")


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://127.0.0.1:5000/callback",
        "http://evil.example/callback",
        "http://127.0.0.1:5000@evil.example/callback",
        "http://127.0.0.1.evil.example:5000/callback",
        "http://127.0.0.1/callback",
        "http://127.0.0.1:5000/other",
        "http://127.0.0.1:5000/callback?x=1",
        "http://[::1]:5000/callback",
        "",
    ],
)
def test_only_loopback_redirects_are_accepted(browser, redirect_uri):
    _, challenge = pkce_pair()
    response = browser.get(
        "/api/cli/authorize", params=authorize_params(challenge, redirect_uri=redirect_uri)
    )
    assert response.status_code == 400
    assert "location" not in response.headers


def test_localhost_redirect_is_accepted():
    assert cli_auth.validate_loopback_redirect("http://localhost:8765/callback")


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": None},
        {"state": "short"},
        {"code_challenge_method": "plain"},
        {"code_challenge": "too-short"},
    ],
)
def test_state_and_pkce_parameters_are_required(browser, overrides):
    _, challenge = pkce_pair()
    response = browser.get("/api/cli/authorize", params=authorize_params(challenge, **overrides))
    assert response.status_code == 400


def test_confirm_page_is_not_cacheable_or_frameable(browser):
    _, challenge = pkce_pair()
    response = browser.get("/api/cli/authorize", params=authorize_params(challenge))
    assert response.status_code == 200
    assert "Allow Manifest CLI on this computer?" in response.text
    assert "ada@example.com" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


def test_allow_link_is_bound_to_the_session(browser):
    _, challenge = pkce_pair()
    params = authorize_params(challenge, confirm="0" * 64)
    response = browser.get("/api/cli/authorize", params=params)
    assert response.status_code == 403 and "location" not in response.headers


def test_cancel_returns_access_denied_with_state(browser):
    _, challenge = pkce_pair()
    response = browser.get("/api/cli/authorize", params=authorize_params(challenge, deny="1"))
    assert response.status_code == 303
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query == {"error": ["access_denied"], "state": [STATE]}


def test_a_cli_token_cannot_approve_another_cli(browser, sessions):  # noqa: F811
    verifier, challenge = pkce_pair()
    token = exchange(browser, approve(browser, challenge), verifier).json()["access_token"]
    cli_browser = TestClient(browser.app, follow_redirects=False)
    cli_browser.cookies.set("session_token", token)
    response = cli_browser.get("/api/cli/authorize", params=authorize_params(pkce_pair()[1]))
    assert response.status_code == 303 and response.headers["location"].startswith("/login?")


# -- token -----------------------------------------------------------------


def test_full_flow_mints_a_labelled_longer_lived_cli_session(browser, sessions):  # noqa: F811
    verifier, challenge = pkce_pair()
    response = exchange(browser, approve(browser, challenge), verifier)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["label"] == "Manifest CLI · ada-mbp"
    assert body["user"] == {"user_id": "u1", "email": "ada@example.com"}
    assert response.headers["cache-control"] == "no-store"

    claims = current_user.decode_session_token(body["access_token"])
    assert claims["kind"] == "cli" and claims["sub"] == "u1"
    assert claims["exp"] - time.time() > 29 * 24 * 3600
    row = sessions.rows[claims["sid"]]
    assert row["user_agent"] == "Manifest CLI · ada-mbp"
    assert sessions_service.session_kind(row["user_agent"]) == "cli"
    assert [e for e, _ in sessions.events] == ["cli_session_created"]

    # The bearer token works on REST and keeps its label (no user-agent overwrite).
    api = TestClient(browser.app)
    me = api.get("/whoami", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json() == {"user_id": "u1"}
    assert (claims["sid"], True) in sessions.touches
    assert row["idle_timeout"] == sessions_service.CLI_SESSION_IDLE_TIMEOUT_SECONDS


def test_cli_session_keeps_the_original_sign_in_time(browser):
    browser_claims = current_user.decode_session_token(browser.cookies.get("session_token"))
    verifier, challenge = pkce_pair()
    time.sleep(1.1)
    token = exchange(browser, approve(browser, challenge), verifier).json()["access_token"]
    assert current_user.decode_session_token(token)["auth_iat"] == browser_claims["auth_iat"]


def test_wrong_verifier_is_rejected(browser):
    _, challenge = pkce_pair()
    other_verifier, _ = pkce_pair()
    response = exchange(browser, approve(browser, challenge), other_verifier)
    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_code_is_single_use(browser):
    verifier, challenge = pkce_pair()
    code = approve(browser, challenge)
    assert exchange(browser, code, verifier).status_code == 200
    again = exchange(browser, code, verifier)
    assert again.status_code == 400 and "already used" in again.json()["error_description"]


def test_redirect_uri_must_match(browser):
    verifier, challenge = pkce_pair()
    response = exchange(
        browser, approve(browser, challenge), verifier, redirect_uri="http://127.0.0.1:1/callback"
    )
    assert response.status_code == 400


def test_code_expires(browser, monkeypatch):
    verifier, challenge = pkce_pair()
    code = approve(browser, challenge)
    real_time = time.time
    monkeypatch.setattr(
        cli_auth.time, "time", lambda: real_time() - cli_auth.CODE_TTL_SECONDS - 120
    )
    stale = approve(browser, challenge)
    monkeypatch.setattr(cli_auth.time, "time", real_time)
    response = exchange(browser, stale, verifier)
    assert response.status_code == 400 and "expired" in response.json()["error_description"]
    assert exchange(browser, code, verifier).status_code == 200


def test_tampered_code_is_rejected(browser):
    verifier, challenge = pkce_pair()
    code = approve(browser, challenge)
    response = exchange(browser, code[:-2] + ("A" if code[-2] != "A" else "B") + code[-1], verifier)
    assert response.status_code == 400


def test_code_is_never_a_session_token(browser):
    _, challenge = pkce_pair()
    code = approve(browser, challenge)
    response = TestClient(browser.app).get("/whoami", headers={"Authorization": f"Bearer {code}"})
    assert response.status_code == 401


def test_guest_cannot_redeem(browser, sessions):  # noqa: F811
    verifier, challenge = pkce_pair()
    code = approve(browser, challenge)
    sessions.guests.add("u1")
    response = exchange(browser, code, verifier)
    assert response.status_code == 403 and response.json()["error"] == "access_denied"


def test_signing_out_the_browser_before_exchange_voids_the_code(browser, sessions):  # noqa: F811
    verifier, challenge = pkce_pair()
    code = approve(browser, challenge)
    for row in sessions.rows.values():
        row["revoked"] = True
    assert exchange(browser, code, verifier).status_code == 400


def test_logout_revokes_the_cli_session(browser, sessions):  # noqa: F811
    verifier, challenge = pkce_pair()
    token = exchange(browser, approve(browser, challenge), verifier).json()["access_token"]
    api = TestClient(browser.app)
    headers = {"Authorization": f"Bearer {token}"}
    assert api.get("/whoami", headers=headers).status_code == 200
    assert api.post("/api/auth/logout", headers=headers).json() == {"ok": True}
    assert api.get("/whoami", headers=headers).status_code == 401
    # The approving browser session is untouched.
    assert browser.get("/whoami").status_code == 200


def test_session_label_is_sanitised():
    assert cli_auth.session_label("ada's <mbp>\n") == "Manifest CLI · ada-s-mbp"
    assert cli_auth.session_label("") == "Manifest CLI · unknown host"


# -- fresh sign-in (step-up) ---------------------------------------------------


def _stale_browser(app, monkeypatch, age_seconds: int) -> TestClient:
    real_now = current_user.datetime.now
    monkeypatch.setattr(
        current_user,
        "datetime",
        type(
            "FrozenDatetime",
            (),
            {"now": staticmethod(lambda tz=None: real_now(tz) - timedelta(seconds=age_seconds))},
        ),
    )
    token = current_user.create_session_token("u1", "ada@example.com")
    monkeypatch.undo()
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("session_token", token)
    return client


def test_stale_sign_in_goes_through_open_media_again(app, sessions, monkeypatch):  # noqa: F811
    browser = _stale_browser(app, monkeypatch, cli_auth_routes.STEP_UP_SECONDS + 60)
    monkeypatch.setattr(cli_auth_routes, "DEMO_MODE", False)
    _, challenge = pkce_pair()
    for extra in ({}, {"confirm": "0" * 64}):
        response = browser.get("/api/cli/authorize", params=authorize_params(challenge, **extra))
        assert response.status_code == 303
        location = urlsplit(response.headers["location"])
        assert location.path == "/api/auth/open-media/start"
        next_path = parse_qs(location.query)["next"][0]
        next_query = parse_qs(urlsplit(next_path).query)
        assert next_query["reauth"] == ["1"] and "confirm" not in next_query
        assert next_query["state"] == [STATE]
        assert auth_routes.safe_next(next_path) == next_path


def test_reauth_does_not_loop(app, sessions, monkeypatch):  # noqa: F811
    browser = _stale_browser(app, monkeypatch, cli_auth_routes.STEP_UP_SECONDS + 60)
    monkeypatch.setattr(cli_auth_routes, "DEMO_MODE", False)
    _, challenge = pkce_pair()
    response = browser.get("/api/cli/authorize", params=authorize_params(challenge, reauth="1"))
    assert response.status_code == 401 and "location" not in response.headers


def test_cancel_works_without_a_fresh_sign_in(app, sessions, monkeypatch):  # noqa: F811
    browser = _stale_browser(app, monkeypatch, cli_auth_routes.STEP_UP_SECONDS + 60)
    monkeypatch.setattr(cli_auth_routes, "DEMO_MODE", False)
    _, challenge = pkce_pair()
    response = browser.get("/api/cli/authorize", params=authorize_params(challenge, deny="1"))
    assert response.status_code == 303 and response.headers["location"].startswith(LOOPBACK)


def test_fresh_sign_in_is_inherited_by_the_cli_session(browser, monkeypatch):
    monkeypatch.setattr(cli_auth_routes, "DEMO_MODE", False)
    verifier, challenge = pkce_pair()
    token = exchange(browser, approve(browser, challenge), verifier).json()["access_token"]
    assert time.time() - current_user.decode_session_token(token)["auth_iat"] < 60
