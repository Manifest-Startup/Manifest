"""OAuth for AI agents on the Manifest MCP server (ADR 0004).

Discovery, stateless registration, metadata-document clients, redirect rules, PKCE,
one-time codes, refresh rotation, revocation and the agent session kind.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from app.auth import current_user
from app.auth.current_user import require_user_id
from app.routes import agent_oauth_routes
from app.services.identity import agent_oauth, sessions as sessions_service
from cli_fakes import pkce_pair, sessions  # noqa: F401 - pytest fixture
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

REDIRECT = "http://127.0.0.1:33418/callback"
STATE = "agent-state-123"


@pytest.fixture
def app(sessions, monkeypatch):  # noqa: F811
    monkeypatch.setattr(agent_oauth_routes, "DEMO_MODE", False)
    monkeypatch.setattr(agent_oauth_routes, "is_session_active", sessions.active)
    monkeypatch.setattr(agent_oauth_routes, "revoke_session", sessions.revoke)
    monkeypatch.setattr(agent_oauth_routes, "_is_guest", lambda uid: uid in sessions.guests)
    monkeypatch.setattr(
        agent_oauth_routes,
        "record_security_event",
        lambda event, **kw: sessions.events.append((event, kw)),
    )
    application = FastAPI()
    application.include_router(agent_oauth_routes.router)

    @application.get("/whoami")
    def whoami(request_user: str = Depends(require_user_id)):
        return {"user_id": request_user}

    return application


@pytest.fixture
def browser(app):
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("session_token", current_user.create_session_token("u1", "ada@example.com"))
    return client


def register(client: TestClient, **overrides) -> dict:
    body = {"client_name": "Claude Code", "redirect_uris": [REDIRECT], **overrides}
    response = client.post("/api/oauth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def authorize_params(client_id: str, challenge: str, **overrides) -> dict:
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "state": STATE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": agent_oauth.RESOURCE,
    }
    params.update(overrides)
    return {k: v for k, v in params.items() if v is not None}


def approve(client: TestClient, client_id: str, challenge: str, **overrides) -> str:
    page = client.get(
        "/api/oauth/authorize", params=authorize_params(client_id, challenge, **overrides)
    )
    assert page.status_code == 200, page.text
    assert "Allow Claude Code to use Manifest?" in page.text
    href = (
        page.text.split('data-testid="agent-allow" href="')[1].split('"')[0].replace("&amp;", "&")
    )
    allowed = client.get(href)
    assert allowed.status_code == 303
    query = parse_qs(urlsplit(allowed.headers["location"]).query)
    assert query["state"] == [STATE] and query["iss"] == [agent_oauth.ISSUER]
    return query["code"][0]


def exchange(client: TestClient, client_id: str, code: str, verifier: str, **extra):
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT,
        **extra,
    }
    return client.post("/api/oauth/token", data=form)


def connect(browser: TestClient) -> tuple[str, dict]:
    client_id = register(browser)["client_id"]
    verifier, challenge = pkce_pair()
    code = approve(browser, client_id, challenge)
    response = exchange(TestClient(browser.app), client_id, code, verifier)
    assert response.status_code == 200, response.text
    return client_id, response.json()


# -- discovery ---------------------------------------------------------------------


def test_discovery_documents_point_at_each_other(app):
    client = TestClient(app)
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == "https://manifeststartup.com/mcp"
    assert client.get("/.well-known/oauth-protected-resource").json() == resource
    server = client.get("/.well-known/oauth-authorization-server").json()
    assert resource["authorization_servers"] == [server["issuer"]]
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert server["client_id_metadata_document_supported"] is True
    assert set(server["grant_types_supported"]) == {"authorization_code", "refresh_token"}


# -- registration ------------------------------------------------------------------


def test_registration_is_stateless_and_signed(app):
    client = TestClient(app)
    registered = register(client, client_name="Cursor <script>")
    assert registered["client_id"].startswith("mcp_")
    assert "<" not in registered["client_name"]
    resolved = agent_oauth.resolve_client(registered["client_id"])
    assert resolved.redirect_uris == (REDIRECT,)
    tampered = registered["client_id"][:-3] + (
        "AAA" if not registered["client_id"].endswith("AAA") else "BBB"
    )
    with pytest.raises(agent_oauth.AgentOAuthError):
        agent_oauth.resolve_client(tampered)


@pytest.mark.parametrize(
    "uri",
    [
        "javascript:alert(1)",
        "data:text/html,hi",
        "http://evil.example/callback",
        "https://good.example/cb#frag",
        "https://user@evil.example/cb",
        "file:///etc/passwd",
    ],
)
def test_unsafe_redirect_uris_are_refused(app, uri):
    response = TestClient(app).post("/api/oauth/register", json={"redirect_uris": [uri]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


@pytest.mark.parametrize(
    "uri",
    [
        "https://claude.ai/api/mcp/auth_callback",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "cursor://anysphere.cursor-mcp/oauth/callback",
        "vscode://vscode.github-authentication/did-authenticate",
        "http://localhost:6274/oauth/callback",
        "http://[::1]:8080/cb",
    ],
)
def test_real_client_redirects_are_accepted(uri):
    assert agent_oauth.validate_redirect_uri(uri) == uri


def test_confidential_clients_are_refused(app):
    response = TestClient(app).post(
        "/api/oauth/register",
        json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "client_secret_basic"},
    )
    assert response.status_code == 400


def test_loopback_redirects_may_change_port_but_nothing_else():
    registered = ("http://127.0.0.1:33418/callback",)
    assert agent_oauth.redirect_matches("http://127.0.0.1:51000/callback", registered)
    assert not agent_oauth.redirect_matches("http://127.0.0.1:51000/other", registered)
    assert not agent_oauth.redirect_matches("http://localhost:51000/callback", registered)
    assert not agent_oauth.redirect_matches("https://claude.ai/x", ("https://claude.ai/y",))


@pytest.mark.parametrize(
    "url", ["https://client.example/", "https://10.0.0.1/meta.json", "https://localhost/meta.json"]
)
def test_metadata_document_urls_must_be_public_https_with_a_path(url):
    with pytest.raises(agent_oauth.AgentOAuthError):
        agent_oauth._fetch_metadata_document(url)


def test_metadata_document_must_name_itself(monkeypatch):
    class Response:
        status_code = 200
        content = b'{"client_id": "https://evil.example/meta.json", "redirect_uris": ["https://x.example/cb"]}'

    monkeypatch.setattr(agent_oauth.safe_http, "safe_request", lambda *a, **k: Response())
    with pytest.raises(agent_oauth.AgentOAuthError, match="must equal its URL"):
        agent_oauth._fetch_metadata_document("https://client.example/meta.json")


def test_metadata_document_clients(monkeypatch):
    url = "https://client.example/oauth/metadata.json"
    monkeypatch.setattr(
        agent_oauth,
        "_fetch_metadata_document",
        lambda u: {
            "client_id": u,
            "client_name": "Example",
            "redirect_uris": ["https://client.example/cb"],
        },
    )
    client = agent_oauth.resolve_client(url)
    assert client.name == "Example" and client.verified_domain == "client.example"
    assert agent_oauth.session_label(client) == "AI agent · Example (client.example)"


# -- authorization -----------------------------------------------------------------


def test_signed_out_people_sign_in_first(app):
    client_id = register(TestClient(app))["client_id"]
    _, challenge = pkce_pair()
    response = TestClient(app, follow_redirects=False).get(
        "/api/oauth/authorize", params=authorize_params(client_id, challenge)
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=%2Fapi%2Foauth%2Fauthorize")


def test_unregistered_redirect_is_shown_not_followed(browser):
    client_id = register(browser)["client_id"]
    _, challenge = pkce_pair()
    response = browser.get(
        "/api/oauth/authorize",
        params=authorize_params(client_id, challenge, redirect_uri="https://evil.example/cb"),
    )
    assert response.status_code == 400 and "location" not in response.headers


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"code_challenge_method": "plain"}, "invalid_request"),
        ({"response_type": "token"}, "unsupported_response_type"),
        ({"resource": "https://other.example/mcp"}, "invalid_target"),
        ({"scope": "admin"}, "invalid_scope"),
    ],
)
def test_bad_requests_redirect_with_an_error(browser, overrides, error):
    client_id = register(browser)["client_id"]
    _, challenge = pkce_pair()
    response = browser.get(
        "/api/oauth/authorize", params=authorize_params(client_id, challenge, **overrides)
    )
    assert response.status_code == 303
    assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == [error]


def test_stale_sign_in_goes_through_open_media_again(app, monkeypatch):
    client = TestClient(app, follow_redirects=False)
    client_id = register(client)["client_id"]
    monkeypatch.setattr(agent_oauth_routes, "_signed_in_recently", lambda payload: False)
    client.cookies.set("session_token", current_user.create_session_token("u1", "ada@example.com"))
    _, challenge = pkce_pair()
    response = client.get("/api/oauth/authorize", params=authorize_params(client_id, challenge))
    assert response.headers["location"].startswith("/api/auth/open-media/start?")


def test_deny_returns_access_denied(browser):
    client_id = register(browser)["client_id"]
    _, challenge = pkce_pair()
    response = browser.get(
        "/api/oauth/authorize", params=authorize_params(client_id, challenge, deny="1")
    )
    assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == ["access_denied"]


def test_forged_allow_link_is_refused(browser):
    client_id = register(browser)["client_id"]
    _, challenge = pkce_pair()
    response = browser.get(
        "/api/oauth/authorize", params=authorize_params(client_id, challenge, confirm="0" * 64)
    )
    assert response.status_code == 403


# -- tokens ------------------------------------------------------------------------


def test_full_flow_gives_a_revocable_agent_session(browser, sessions):  # noqa: F811
    client_id, tokens = connect(browser)
    assert (
        tokens["token_type"] == "Bearer"
        and tokens["expires_in"] == agent_oauth.ACCESS_TOKEN_SECONDS
    )
    claims = current_user.decode_session_token(tokens["access_token"])
    assert claims["kind"] == "agent" and claims["sub"] == "u1"
    row = sessions.rows[claims["sid"]]
    assert row["user_agent"] == "AI agent · Claude Code"
    assert sessions_service.session_kind(row["user_agent"]) == "agent"
    api = TestClient(browser.app)
    assert api.get(
        "/whoami", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    ).json() == {"user_id": "u1"}
    assert sessions.events[-1][0] == "agent_session_created"


def test_codes_work_once_and_need_the_verifier_and_client(browser):
    client_id = register(browser)["client_id"]
    other_client = register(browser, client_name="Other")["client_id"]
    verifier, challenge = pkce_pair()
    code = approve(browser, client_id, challenge)
    api = TestClient(browser.app)
    wrong_verifier, _ = pkce_pair()
    assert exchange(api, client_id, code, wrong_verifier).json()["error"] == "invalid_grant"
    assert exchange(api, other_client, code, verifier).json()["error"] == "invalid_grant"
    assert exchange(api, client_id, code, verifier).status_code == 200
    assert exchange(api, client_id, code, verifier).json()["error"] == "invalid_grant"


def test_cli_codes_are_not_agent_codes(browser):
    from app.services.identity import cli_auth

    client_id = register(browser)["client_id"]
    verifier, challenge = pkce_pair()
    cli_code = cli_auth.issue_code(
        user_id="u1",
        email=None,
        browser_session_id=None,
        auth_iat=None,
        redirect_uri=REDIRECT,
        code_challenge=challenge,
    )
    assert (
        exchange(TestClient(browser.app), client_id, cli_code, verifier).json()["error"]
        == "invalid_grant"
    )


def test_refresh_rotates_and_old_refresh_tokens_stop_working(browser, sessions):  # noqa: F811
    client_id, tokens = connect(browser)
    api = TestClient(browser.app)
    refreshed = api.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    new = refreshed.json()
    old_sid = current_user.decode_session_token(tokens["access_token"])["sid"]
    assert sessions.rows[old_sid]["revoked"]
    assert current_user.decode_session_token(new["access_token"])["email"] == "ada@example.com"
    replay = api.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert replay.json()["error"] == "invalid_grant"
    other = register(browser, client_name="Other")["client_id"]
    stolen = api.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": other,
            "refresh_token": new["refresh_token"],
        },
    )
    assert stolen.json()["error"] == "invalid_grant"


def test_revoke_disconnects_the_agent(browser, sessions):  # noqa: F811
    client_id, tokens = connect(browser)
    api = TestClient(browser.app)
    assert api.post("/api/oauth/revoke", data={"token": tokens["access_token"]}).status_code == 200
    sid = current_user.decode_session_token(tokens["access_token"])["sid"]
    assert sessions.rows[sid]["revoked"]
    refreshed = api.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
        },
    )
    assert refreshed.json()["error"] == "invalid_grant"


def test_agent_tokens_cannot_approve_other_agents(browser):
    _, tokens = connect(browser)
    client = TestClient(browser.app, follow_redirects=False)
    client.cookies.set("session_token", tokens["access_token"])
    client_id = register(client)["client_id"]
    _, challenge = pkce_pair()
    response = client.get("/api/oauth/authorize", params=authorize_params(client_id, challenge))
    assert response.headers["location"].startswith("/login?")


def test_guests_cannot_connect_agents(browser, sessions):  # noqa: F811
    sessions.guests.add("u1")
    client_id = register(browser)["client_id"]
    _, challenge = pkce_pair()
    response = browser.get("/api/oauth/authorize", params=authorize_params(client_id, challenge))
    assert response.headers["location"].startswith("/login?")
