"""Continue with Open Media: state + nonce cookie, account matching, guest merge, redirects."""

from __future__ import annotations

import contextlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.routes import auth_routes
from app.security.cookies import SIGN_IN_NONCE_COOKIE_NAME
from app.services.identity import guest_workspace
from app.services.integrations.open_media import identity, store
from app.services.integrations.open_media import client as om_client
from app.services.integrations.open_media.client import OpenMediaClient
from app.services.shared import cache
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -- fakes ------------------------------------------------------------------


class FakeUsers:
    """The ``users`` rows and Open Media links the matcher can see."""

    def __init__(self):
        self.users: dict[str, dict] = {}
        self.links: dict[str, str] = {}  # manifest user_id -> om_user_id
        self.saved: dict[str, dict] = {}

    def add(self, user_id, email, *, om_id=None, guest=False, disabled=False):
        self.users[user_id] = {
            "user_id": user_id,
            "email": email,
            "is_guest": guest,
            "disabled_at": "2026-01-01" if disabled else None,
        }
        if om_id:
            self.links[user_id] = om_id


class FakeCursor:
    def __init__(self, db: FakeUsers):
        self.db = db

    def execute(self, sql, params=()):
        assert "INSERT INTO users" in sql, sql
        user_id, email = params
        self.db.add(user_id, email)


@pytest.fixture
def db(monkeypatch):
    fake = FakeUsers()

    @contextlib.contextmanager
    def connection():
        class Conn:
            def cursor(self):
                return contextlib.nullcontext(FakeCursor(fake))

            def commit(self):
                pass

        yield Conn()

    monkeypatch.setattr(identity, "get_db_connection", connection)
    monkeypatch.setattr(
        identity,
        "_user_linked_to",
        lambda cur, om_id: next(
            (
                uid
                for uid, linked in fake.links.items()
                if linked == om_id and not fake.users[uid]["is_guest"]
            ),
            None,
        ),
    )
    monkeypatch.setattr(identity, "_linked_om_user_id", lambda cur, uid: fake.links.get(uid))
    monkeypatch.setattr(
        identity, "_load_user", lambda cur, uid: dict(fake.users[uid]) if uid in fake.users else None
    )
    monkeypatch.setattr(
        identity,
        "_user_by_email",
        lambda cur, email: next(
            (
                dict(u)
                for u in fake.users.values()
                if u["email"].lower() == email.lower() and not u["is_guest"]
            ),
            None,
        ),
    )

    def save_link(user_id, **kw):
        fake.links[user_id] = kw["om_user_id"]
        fake.saved[user_id] = kw
        return {"om_user_id": kw["om_user_id"], "handle": kw["handle"]}

    monkeypatch.setattr(store, "save_link", save_link)
    return fake


@pytest.fixture
def om(monkeypatch):
    """Open Media's token endpoint and ``/v1/connected/me``."""
    monkeypatch.setenv("OPEN_MEDIA_API_BASE", "https://om.test")
    answers = {"me": {}, "token": (200, {"access_token": "at", "refresh_token": "rt"})}
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/oauth/token":
            status, body = answers["token"]
            return httpx.Response(status, json=body)
        if request.url.path == "/v1/connected/me":
            return httpx.Response(200, json=answers["me"])
        return httpx.Response(404, json={"error": "not_found"})

    om_client.set_client(OpenMediaClient(transport=httpx.MockTransport(handler), sleep=lambda s: None))
    cache._reset_for_tests()
    yield {"answers": answers, "calls": calls}
    om_client.set_client(None)
    cache._reset_for_tests()


def _me(**overrides):
    record = {
        "id": "om-1",
        "handle": "ada",
        "display_name": "Ada",
        "email": "Ada@Example.test",
        "email_verified": True,
        "has_profile": True,
    }
    record.update(overrides)
    return record


def _start(**kwargs):
    url, nonce = identity.authorize_url(**kwargs)
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    return query, identity.nonce_cookie_value(nonce)


def _sign_in(session_user_id=None, **start_kwargs):
    query, cookie = _start(**start_kwargs)
    return identity.complete_sign_in(
        code="the-code", state=query["state"], nonce_cookie=cookie, session_user_id=session_user_id
    )


# -- the authorize URL --------------------------------------------------------


def test_authorize_url_uses_pkce_s256_signed_state_and_the_new_callback(monkeypatch):
    monkeypatch.setenv("OPEN_MEDIA_API_BASE", "https://om.test")
    url, nonce = identity.authorize_url(next_path="/ideas/42", login_hint="ana@example.test")
    parts = urlsplit(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://om.test/authorize"
    assert q["response_type"] == "code"
    assert q["client_id"] == "https://manifeststartup.com/oauth/open-media-client.json"
    assert q["redirect_uri"] == "https://manifeststartup.com/api/auth/open-media/callback"
    assert q["scope"] == "account"
    assert q["code_challenge_method"] == "S256"
    assert q["code_challenge"] == identity.code_challenge(identity.code_verifier(nonce))
    assert q["login_hint"] == "ana@example.test"
    assert identity._read_state(q["state"])["x"] == "/ideas/42"


# -- matching the Manifest account ---------------------------------------------


def test_links_by_open_media_id_first(db, om):
    db.add("existing", "old-address@example.test", om_id="om-1")
    db.add("same-email", "ada@example.test")
    om["answers"]["me"] = _me()
    result = _sign_in()
    assert (result.user_id, result.matched_by) == ("existing", "open_media_id")
    assert db.saved["existing"]["refresh_token"] == "rt"
    form = parse_qs(om["calls"][0].content.decode())
    assert form["grant_type"] == ["authorization_code"] and form["code"] == ["the-code"]
    assert om["calls"][1].headers["authorization"] == "Bearer at"


def test_auto_links_an_existing_account_by_verified_email_case_insensitively(db, om):
    db.add("password-user", "ada@example.test")
    om["answers"]["me"] = _me(email="  ADA@example.TEST ")
    result = _sign_in()
    assert (result.user_id, result.matched_by) == ("password-user", "email")
    assert db.links["password-user"] == "om-1"


def test_creates_a_full_account_for_a_new_person(db, om):
    om["answers"]["me"] = _me(email="new@example.test")
    result = _sign_in()
    assert result.matched_by == "new"
    assert db.users[result.user_id]["email"] == "new@example.test"
    assert db.users[result.user_id]["is_guest"] is False
    assert db.links[result.user_id] == "om-1"


def test_unverified_email_is_refused_and_nothing_is_created(db, om):
    db.add("password-user", "ada@example.test")
    om["answers"]["me"] = _me(email_verified=False)
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        _sign_in()
    assert exc.value.code == "unverified_email"
    assert list(db.users) == ["password-user"] and db.links == {} and db.saved == {}


def test_missing_email_is_refused(db, om):
    om["answers"]["me"] = _me(email=None)
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        _sign_in()
    assert exc.value.code == "no_email" and db.users == {}


def test_a_person_without_an_open_media_profile_can_still_sign_in(db, om):
    om["answers"]["me"] = {"id": "om-2", "email": "p@example.test", "email_verified": True,
                           "has_profile": False}
    result = _sign_in()
    assert result.matched_by == "new" and result.account.has_profile is False
    assert db.saved[result.user_id]["handle"] == ""


def test_email_match_linked_to_another_open_media_account_is_refused(db, om):
    db.add("password-user", "ada@example.test", om_id="om-other")
    om["answers"]["me"] = _me()
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        _sign_in()
    assert exc.value.code == "linked_elsewhere"


def test_disabled_accounts_cannot_sign_in(db, om):
    db.add("gone", "ada@example.test", disabled=True)
    om["answers"]["me"] = _me()
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        _sign_in()
    assert exc.value.code == "account_disabled"


def test_a_signed_in_account_reconnects_even_with_another_email(db, om):
    db.add("me", "work@example.test")
    om["answers"]["me"] = _me(email_verified=False)
    result = _sign_in(session_user_id="me", user_id="me")
    assert (result.user_id, result.matched_by) == ("me", "session")


def test_reconnect_state_from_another_session_is_ignored(db, om):
    db.add("victim", "victim@example.test")
    om["answers"]["me"] = _me(email="attacker@example.test")
    result = _sign_in(session_user_id="someone-else", user_id="victim")
    assert result.user_id != "victim" and result.matched_by == "new"


def test_reconnect_refuses_an_open_media_account_linked_elsewhere(db, om):
    db.add("me", "me@example.test")
    db.add("other", "other@example.test", om_id="om-1")
    om["answers"]["me"] = _me()
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        _sign_in(session_user_id="me", user_id="me")
    assert exc.value.code == "linked_elsewhere"


def test_guest_is_only_returned_for_the_guest_session_that_started_it(db, om):
    om["answers"]["me"] = _me(email="g@example.test")
    assert _sign_in(session_user_id="guest-1", guest_user_id="guest-1").guest_user_id == "guest-1"
    assert _sign_in(session_user_id="guest-2", guest_user_id="guest-1").guest_user_id is None


# -- state and nonce cookie -------------------------------------------------------


def test_tampered_state_is_rejected_before_any_request(db, om):
    query, cookie = _start()
    body, sig = query["state"].split(".")
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        identity.complete_sign_in(code="c", state=f"{body}x.{sig}", nonce_cookie=cookie,
                                  session_user_id=None)
    assert exc.value.code == "invalid_state" and om["calls"] == []


@pytest.mark.parametrize("cookie", [None, "", "forged.cookie", "other-nonce"])
def test_state_must_match_the_signed_nonce_cookie(db, om, cookie):
    query, _ = _start()
    if cookie == "other-nonce":
        cookie = identity.nonce_cookie_value("another-nonce")
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        identity.complete_sign_in(code="c", state=query["state"], nonce_cookie=cookie,
                                  session_user_id=None)
    assert exc.value.code == "invalid_state" and om["calls"] == []


def test_replayed_and_expired_states_are_rejected(db, om, monkeypatch):
    om["answers"]["me"] = _me()
    query, cookie = _start()
    identity.complete_sign_in(code="c", state=query["state"], nonce_cookie=cookie,
                              session_user_id=None)
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        identity.complete_sign_in(code="c", state=query["state"], nonce_cookie=cookie,
                                  session_user_id=None)
    assert exc.value.code == "replayed"

    query, cookie = _start()
    monkeypatch.setattr(identity.time, "time", lambda: 10**12)
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        identity.complete_sign_in(code="c", state=query["state"], nonce_cookie=cookie,
                                  session_user_id=None)
    assert exc.value.code == "expired"


def test_failed_code_exchange_stores_nothing(db, om):
    om["answers"]["token"] = (400, {"error": "invalid_grant"})
    with pytest.raises(identity.OpenMediaLinkError) as exc:
        _sign_in()
    assert exc.value.code == "failed" and db.users == {} and db.saved == {}


# -- guest merge (the existing merge path) -----------------------------------------


class GuestCursor:
    def __init__(self, row):
        self.row = row
        self.sql: list[str] = []

    def execute(self, sql, params=()):
        self.sql.append(sql)

    def fetchone(self):
        return self.row


def _guest_db(monkeypatch, row):
    cur = GuestCursor(row)

    @contextlib.contextmanager
    def connection():
        class Conn:
            def cursor(self):
                return contextlib.nullcontext(cur)

            def commit(self):
                pass

        yield Conn()

    import app.db.database as database

    monkeypatch.setattr(database, "get_db_connection", connection)
    return cur


def test_claim_guest_workspace_merges_with_the_stored_secret(monkeypatch):
    _guest_db(monkeypatch, {"is_guest": True, "guest_merge_secret": "s3cret"})
    calls = []
    monkeypatch.setattr(
        guest_workspace,
        "merge_guest_workspace_sql",
        lambda cur, target, guest, secret: calls.append((target, guest, secret)) or 3,
    )
    assert guest_workspace.claim_guest_workspace("full", "guest") == 3
    assert calls == [("full", "guest", "s3cret")]


@pytest.mark.parametrize(
    "row", [None, {"is_guest": False, "guest_merge_secret": None}, {"is_guest": True}]
)
def test_claim_guest_workspace_is_a_no_op_once_claimed(monkeypatch, row):
    _guest_db(monkeypatch, row)
    monkeypatch.setattr(
        guest_workspace, "merge_guest_workspace_sql", lambda *a: pytest.fail("must not merge")
    )
    assert guest_workspace.claim_guest_workspace("full", "guest") == 0


class MergeCursor:
    """Enough of Postgres for ``merge_guest_workspace_sql`` end to end."""

    def __init__(self):
        self.users = {
            "guest": {"is_guest": True, "guest_merge_secret": "s3cret", "guest_expires_at": None},
            "full": {"is_guest": False},
        }
        self.ideas = {"i1": "guest", "i2": "guest", "i3": "full"}
        self._result = None

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        if text.startswith("SELECT is_guest, guest_merge_secret, guest_expires_at"):
            self._result = [dict(self.users[params[0]])] if params[0] in self.users else []
        elif text.startswith("SELECT is_guest, guest_merge_secret FROM users"):
            self._result = [dict(self.users[params[0]])] if params[0] in self.users else []
        elif text.startswith("SELECT is_guest FROM users"):
            self._result = [{"is_guest": self.users[params[0]]["is_guest"]}]
        elif text.startswith("UPDATE ideas SET user_id"):
            target, guest = params
            moved = [i for i, owner in self.ideas.items() if owner == guest]
            for idea in moved:
                self.ideas[idea] = target
            self._result = [{"idea_id": i} for i in moved]
        elif text.startswith("UPDATE users SET is_guest = FALSE"):
            self.users[params[0]].update(is_guest=False, guest_merge_secret=None)
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result


def test_guest_ideas_move_to_the_signed_in_account_and_retries_are_safe(monkeypatch):
    cur = MergeCursor()

    @contextlib.contextmanager
    def connection():
        class Conn:
            def cursor(self):
                return contextlib.nullcontext(cur)

            def commit(self):
                pass

        yield Conn()

    import app.db.database as database

    monkeypatch.setattr(database, "get_db_connection", connection)
    assert guest_workspace.claim_guest_workspace("full", "guest") == 2
    assert cur.ideas == {"i1": "full", "i2": "full", "i3": "full"}
    assert cur.users["guest"]["is_guest"] is False
    # A retried callback finds the guest already claimed: nothing moves, nothing is lost.
    assert guest_workspace.claim_guest_workspace("full", "guest") == 0
    assert cur.ideas == {"i1": "full", "i2": "full", "i3": "full"}


# -- routes -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("/ideas/42?tab=deck#top", "/ideas/42?tab=deck#top"),
        ("/account", "/account"),
        (None, "/ideas"),
        ("", "/ideas"),
        ("https://evil.example/x", "/ideas"),
        ("//evil.example/x", "/ideas"),
        ("/\\evil.example", "/ideas"),
        ("/%0d%0aSet-Cookie:x", "/%0d%0aSet-Cookie:x"),
        ("/ok\r\nSet-Cookie: x=1", "/ideas"),
        ("javascript:alert(1)", "/ideas"),
        ("ideas", "/ideas"),
        ("/login?error=x", "/ideas"),
        ("/api/auth/logout", "/ideas"),
    ],
)
def test_safe_next_only_allows_same_origin_paths(raw, expected):
    assert auth_routes.safe_next(raw) == expected


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth_routes, "DEMO_MODE", False)
    monkeypatch.setenv("OPEN_MEDIA_API_BASE", "https://om.test")
    state = {"user": None, "guest": False, "merged": [], "sessions": []}
    monkeypatch.setattr(auth_routes, "get_current_user_id_optional", lambda r: state["user"])
    monkeypatch.setattr(auth_routes, "fetch_user_is_guest", lambda db, uid: state["guest"])
    monkeypatch.setattr(auth_routes, "create_database_client", lambda: None)
    monkeypatch.setattr(auth_routes, "_user_email", lambda uid: "me@example.test")
    monkeypatch.setattr(auth_routes, "record_security_event", lambda *a, **k: None)
    monkeypatch.setattr(auth_routes, "_resume_pending_reels", lambda uid: None)
    monkeypatch.setattr(auth_routes, "detect_brute_force", lambda **k: False)
    monkeypatch.setattr(auth_routes, "detect_impossible_travel", lambda **k: False)
    monkeypatch.setattr(
        auth_routes,
        "create_session_token",
        lambda uid, email=None, request=None: state["sessions"].append(uid) or f"jwt-{uid}",
    )

    def claim(target, guest):
        state["merged"].append((target, guest))
        return 2

    monkeypatch.setattr(auth_routes, "claim_guest_workspace", claim)
    app = FastAPI()
    app.include_router(auth_routes.router)
    test_client = TestClient(app, follow_redirects=False)
    test_client.state = state
    return test_client


def _state_of(response):
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return identity._read_state(query["state"][0]), query


def test_start_sets_a_signed_httponly_nonce_cookie_and_redirects(client):
    response = client.get("/api/auth/open-media/start?next=/ideas/7")
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert (location.netloc, location.path) == ("om.test", "/authorize")
    payload, query = _state_of(response)
    assert payload["x"] == "/ideas/7" and "g" not in payload and "u" not in payload
    assert "login_hint" not in query
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SIGN_IN_NONCE_COOKIE_NAME}=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Path=/api/auth/open-media" in cookie and "Max-Age=600" in cookie
    assert identity._nonce_from_cookie(client.cookies.get(SIGN_IN_NONCE_COOKIE_NAME)) == payload["n"]


def test_start_never_puts_an_open_redirect_in_the_state(client):
    payload, _ = _state_of(client.get("/api/auth/open-media/start?next=//evil.example"))
    assert payload["x"] == "/ideas"


def test_start_from_a_guest_session_carries_the_guest_to_merge(client):
    client.state.update(user="guest-1", guest=True)
    payload, query = _state_of(client.get("/api/auth/open-media/start"))
    assert payload["g"] == "guest-1" and "u" not in payload
    assert "login_hint" not in query


def test_start_from_a_signed_in_account_reconnects_with_its_email_as_hint(client):
    client.state.update(user="me", guest=False)
    payload, query = _state_of(client.get("/api/auth/open-media/start?next=/account"))
    assert payload["u"] == "me" and query["login_hint"] == ["me@example.test"]


def test_start_ignores_a_malformed_login_hint(client):
    _, query = _state_of(client.get("/api/auth/open-media/start?login_hint=not-an-email"))
    assert "login_hint" not in query


def test_callback_signs_in_sets_the_session_cookie_and_redirects_to_next(client, db, om):
    om["answers"]["me"] = _me(email="new@example.test")
    start = client.get("/api/auth/open-media/start?next=/ideas/7")
    _, query = _state_of(start)
    response = client.get(f"/api/auth/open-media/callback?code=c&state={query['state'][0]}")
    assert response.status_code == 303
    assert response.headers["location"] == "/ideas/7"
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("session_token=jwt-") and "HttpOnly" in c for c in cookies)
    assert any(c.startswith(f'{SIGN_IN_NONCE_COOKIE_NAME}=""') for c in cookies)
    assert client.state["sessions"] and client.state["merged"] == []


def test_callback_merges_the_guest_workspace_into_the_account(client, db, om):
    db.add("full", "ada@example.test")
    om["answers"]["me"] = _me()
    client.state.update(user="guest-1", guest=True)
    _, query = _state_of(client.get("/api/auth/open-media/start?next=/ideas"))
    response = client.get(f"/api/auth/open-media/callback?code=c&state={query['state'][0]}")
    assert response.headers["location"] == "/ideas?merged=2"
    assert client.state["merged"] == [("full", "guest-1")]
    assert client.state["sessions"] == ["full"]


def test_callback_refuses_unverified_email_with_a_clear_error(client, db, om):
    om["answers"]["me"] = _me(email_verified=False)
    _, query = _state_of(client.get("/api/auth/open-media/start"))
    response = client.get(f"/api/auth/open-media/callback?code=c&state={query['state'][0]}")
    assert response.headers["location"] == "/login?error=unverified_email"
    assert client.state["sessions"] == [] and db.users == {}


def test_callback_without_the_nonce_cookie_is_refused(client, db, om):
    _, query = _state_of(client.get("/api/auth/open-media/start"))
    client.cookies.clear()
    response = client.get(f"/api/auth/open-media/callback?code=c&state={query['state'][0]}")
    assert response.headers["location"] == "/login?error=invalid_state"
    assert om["calls"] == [] and client.state["sessions"] == []


@pytest.mark.parametrize(
    "query, error",
    [
        ("error=access_denied", "cancelled"),
        ("error=server_error", "failed"),
        ("code=c", "failed"),
        ("state=s", "failed"),
        ("code=c&state=garbage", "invalid_state"),
    ],
)
def test_callback_reports_denied_missing_and_bad_state(client, db, om, query, error):
    response = client.get(f"/api/auth/open-media/callback?{query}")
    assert response.headers["location"] == f"/login?error={error}"
    assert client.state["sessions"] == []


def test_demo_mode_signs_in_the_demo_user_without_open_media(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "DEMO_MODE", True)
    monkeypatch.setattr(auth_routes, "_ensure_demo_user", lambda: None)
    response = client.get("/api/auth/open-media/start?next=/account")
    assert response.headers["location"] == "/account"
    assert any(c.startswith("session_token=") for c in response.headers.get_list("set-cookie"))


def test_logout_revokes_the_session_and_clears_cookies(client, monkeypatch):
    revoked = []
    monkeypatch.setattr(
        auth_routes, "get_current_token_payload_optional", lambda r: {"sub": "u1", "sid": "s1"}
    )
    monkeypatch.setattr(auth_routes, "revoke_session", lambda sid, uid: revoked.append((sid, uid)))
    response = client.post("/api/auth/logout")
    assert response.json() == {"ok": True} and revoked == [("s1", "u1")]
    cleared = response.headers.get_list("set-cookie")
    assert any(c.startswith('session_token=""') for c in cleared)


def test_session_tokens_record_the_sign_in_time(monkeypatch):
    from app.auth import current_user

    monkeypatch.setattr(current_user, "create_user_session", lambda uid, request: "sid-1")
    claims = current_user.decode_session_token(current_user.create_session_token("u1", "a@b.c"))
    assert claims["sub"] == "u1" and claims["sid"] == "sid-1"
    assert abs(claims["auth_iat"] - time.time()) < 5
