"""Shared fakes for the Manifest CLI sign-in tests: an in-memory ``user_sessions`` table."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from app.auth import current_user
from app.routes import cli_auth_routes
from app.services.identity import cli_auth
from app.services.shared import cache


@dataclass
class FakeSessions:
    rows: dict[str, dict] = field(default_factory=dict)
    guests: set[str] = field(default_factory=set)
    touches: list[tuple[str, bool]] = field(default_factory=list)
    events: list[tuple[str, dict]] = field(default_factory=list)

    def create(self, user_id, request, *, ttl_days=7, label=None):
        sid = str(uuid.uuid4())
        ua = label or (request.headers.get("user-agent") if request is not None else None)
        self.rows[sid] = {
            "user_id": user_id,
            "user_agent": ua,
            "revoked": False,
            "expires_at": datetime.now(UTC) + timedelta(days=ttl_days),
            "idle_timeout": None,
        }
        return sid

    def active(self, sid, user_id, idle_timeout_seconds=None):
        row = self.rows.get(sid)
        if row is not None:
            row["idle_timeout"] = idle_timeout_seconds
        return bool(row and row["user_id"] == user_id and not row["revoked"])

    def touch(self, sid, request, *, keep_user_agent=False):
        if sid:
            self.touches.append((sid, keep_user_agent))

    def revoke(self, sid, user_id):
        row = self.rows.get(sid)
        if row and row["user_id"] == user_id and not row["revoked"]:
            row["revoked"] = True
            return True
        return False


@pytest.fixture
def sessions(monkeypatch) -> FakeSessions:
    fake = FakeSessions()
    monkeypatch.setattr(current_user, "create_user_session", fake.create)
    monkeypatch.setattr(current_user, "is_session_active", fake.active)
    monkeypatch.setattr(current_user, "touch_session", fake.touch)
    monkeypatch.setattr(current_user, "_is_user_disabled", lambda uid: False)
    monkeypatch.setattr(cli_auth_routes, "is_session_active", fake.active)
    monkeypatch.setattr(cli_auth_routes, "_is_guest", lambda uid: uid in fake.guests)
    monkeypatch.setattr(
        cli_auth_routes,
        "record_security_event",
        lambda event, **kw: fake.events.append((event, kw)),
    )
    from app.routes import auth_routes

    monkeypatch.setattr(auth_routes, "revoke_session", fake.revoke)
    monkeypatch.setattr(auth_routes, "record_security_event", lambda *a, **k: None)
    cache._reset_for_tests()
    cli_auth._reset_for_tests()
    return fake


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge
