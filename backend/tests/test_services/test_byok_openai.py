"""Bring-your-own-key: key resolution, per-key clients, encrypted storage."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from app.graphql.error_masking import should_mask_error
from app.services import ai_credentials, user_ai_key_service
from app.services.ai_credentials import (
    MISSING_KEY_MESSAGE,
    MissingOpenAIKeyError,
    current_openai_key,
    start_thread_with_current_key,
    use_openai_key,
)
from app.services.ai_router import AIRouter
from graphql import GraphQLError

USER_KEY = "sk-user-" + "a" * 32
OTHER_KEY = "sk-other-" + "b" * 32


@pytest.fixture(autouse=True)
def no_platform_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _fake_request():
    return SimpleNamespace(state=SimpleNamespace())


def test_no_key_anywhere_means_ai_unavailable():
    router = AIRouter()
    assert current_openai_key() is None
    assert not router.is_available()
    with pytest.raises(MissingOpenAIKeyError, match="Add your OpenAI API key"):
        _ = router.client


def test_signed_in_users_own_key_is_used(monkeypatch):
    monkeypatch.setattr("app.utils.auth_utils.get_current_user_id_optional", lambda req: "user-1")
    monkeypatch.setattr(user_ai_key_service, "load_user_key", lambda uid: USER_KEY if uid == "user-1" else None)
    token = ai_credentials._request.set(_fake_request())
    try:
        assert current_openai_key() == USER_KEY
        assert AIRouter().is_available()
    finally:
        ai_credentials._request.reset(token)


def test_user_key_beats_platform_key_and_pinned_key_beats_both(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-platform-" + "c" * 30)
    monkeypatch.setattr("app.utils.auth_utils.get_current_user_id_optional", lambda req: "user-1")
    monkeypatch.setattr(user_ai_key_service, "load_user_key", lambda uid: USER_KEY)
    token = ai_credentials._request.set(_fake_request())
    try:
        assert current_openai_key() == USER_KEY
        with use_openai_key(OTHER_KEY):
            assert current_openai_key() == OTHER_KEY
    finally:
        ai_credentials._request.reset(token)


def test_platform_key_is_only_a_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-platform-" + "c" * 30)
    assert (current_openai_key() or "").startswith("sk-platform-")


def test_router_keeps_one_client_per_key():
    router = AIRouter()
    with use_openai_key(USER_KEY):
        first = router.client
        assert router.client is first
    with use_openai_key(OTHER_KEY):
        assert router.client is not first
    assert first.api_key == USER_KEY


def test_background_thread_keeps_callers_key():
    seen: list[str | None] = []
    done = threading.Event()

    def job():
        seen.append(current_openai_key())
        done.set()

    with use_openai_key(USER_KEY):
        start_thread_with_current_key(job)
    assert done.wait(5)
    assert seen == [USER_KEY]


def test_missing_key_message_reaches_the_user_unmasked():
    err = MissingOpenAIKeyError()
    assert not should_mask_error(GraphQLError(str(err), original_error=err))
    assert str(err) == MISSING_KEY_MESSAGE


@pytest.mark.parametrize("bad", ["", "abc", "sk-short", "sk-has space " + "x" * 20, "pk-" + "x" * 40])
def test_malformed_keys_are_rejected_before_calling_openai(bad):
    with pytest.raises(user_ai_key_service.InvalidOpenAIKeyError):
        user_ai_key_service.validate_key(bad)


class _FakeDB:
    """Minimal integrations table for save/load/delete."""

    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}

    def connection(self):
        db = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params):
                self.result = None
                if sql.lstrip().startswith("INSERT"):
                    user_id, service_id, _name, ct, _ver, meta = params
                    db.rows[(user_id, service_id)] = {"access_token_ciphertext": ct, "metadata": meta}
                elif sql.lstrip().startswith("DELETE"):
                    db.rows.pop(tuple(params), None)
                else:
                    self.result = db.rows.get(tuple(params))

            def fetchone(self):
                return self.result

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def cursor(self):
                return Cursor()

            def commit(self):
                pass

        return Conn()


def test_keys_are_stored_encrypted_and_round_trip(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(user_ai_key_service, "get_db_connection", db.connection)
    monkeypatch.setattr(user_ai_key_service, "get_or_create_tenant_dek", lambda kind, tid: b"k" * 32)
    monkeypatch.setattr(user_ai_key_service, "validate_key", lambda key: key.strip())

    assert user_ai_key_service.save_user_key("user-1", f"  {USER_KEY}  ") == USER_KEY[-4:]
    stored = db.rows[("user-1", "openai")]
    assert USER_KEY.encode() not in bytes(stored["access_token_ciphertext"])
    assert json.loads(stored["metadata"]) == {"last4": USER_KEY[-4:]}
    assert user_ai_key_service.load_user_key("user-1") == USER_KEY
    assert user_ai_key_service.key_last4("user-1") == USER_KEY[-4:]

    user_ai_key_service.delete_user_key("user-1")
    assert user_ai_key_service.load_user_key("user-1") is None
    assert user_ai_key_service.key_last4("user-1") is None


def test_openai_key_row_is_hidden_from_integrations_list():
    from app.graphql.schema import _visible_integrations

    rows = [{"service_id": "github"}, {"service_id": "openai"}, {"service_id": "slack"}]
    assert [r["service_id"] for r in _visible_integrations(rows)] == ["github", "slack"]
