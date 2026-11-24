"""Is each connection the person relies on actually working right now?

Answers with the master spec's lifecycle words, per connection:

- ``verified``: Manifest just used it successfully (Open Media: ``GET /v1/connected/me``).
- ``connected``: credentials are held and not expired, but nothing was called to prove it.
- ``authentication_required``: the person has to sign in again (reconnect, or an expired
  token with no way to refresh it).
- ``degraded``: the service didn't answer properly just now; try again later.
- ``disconnected``: nothing is set up.

Only Open Media is called live: it's what goals send through, and one ``/me`` read is cheap.
Other providers are judged from what is stored (expiry, refresh token), so a health check
never spends the person's API credits. Credentials are never returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.integrations.open_media import identity, settings
from app.services.integrations.open_media.client import (
    OpenMediaError,
    OpenMediaNotLinked,
    get_client,
)

VERIFIED = "verified"
CONNECTED = "connected"
AUTH_REQUIRED = "authentication_required"
DEGRADED = "degraded"
DISCONNECTED = "disconnected"
HIDDEN = {"openai", "apollo", "open_media"}  # BYOK keys and Open Media are reported on their own


def _now() -> datetime:
    return datetime.now(UTC)


def _entry(service: str, name: str, state: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "service": service,
        "name": name,
        "state": state,
        "detail": detail,
        "checked_at": _now().isoformat(),
        **extra,
    }


def open_media(user_id: str) -> dict[str, Any]:
    if not settings.enabled():
        return _entry("open_media", "Open Media", DISCONNECTED, "Open Media is off on this server.")
    link = identity.link_status(user_id)
    if not link.get("linked"):
        return _entry(
            "open_media", "Open Media", DISCONNECTED, "Not linked. Sign in with Open Media."
        )
    if link.get("needs_reconnect"):
        return _entry(
            "open_media", "Open Media", AUTH_REQUIRED, "Reconnect Open Media in Settings."
        )
    try:
        me = get_client().connected(user_id, "GET", "")
    except OpenMediaNotLinked:
        return _entry(
            "open_media", "Open Media", AUTH_REQUIRED, "Reconnect Open Media in Settings."
        )
    except OpenMediaError as exc:
        return _entry("open_media", "Open Media", DEGRADED, f"Open Media didn't answer: {exc}")
    handle = me.get("handle") or link.get("handle")
    return _entry(
        "open_media",
        "Open Media",
        VERIFIED,
        f"Signed in as @{handle}." if handle else "Signed in.",
        handle=handle,
    )


def _stored(row: dict[str, Any]) -> dict[str, Any]:
    from app.services.integrations.connections import display_name

    service = str(row.get("service_id") or "")
    name = display_name(service)
    has_token = bool(row.get("access_token") or row.get("access_token_ciphertext"))
    can_refresh = bool(row.get("refresh_token") or row.get("refresh_token_ciphertext"))
    if not has_token:
        return _entry(service, name, AUTH_REQUIRED, f"Finish connecting {name} in Settings.")
    expires = row.get("expires_at")
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            expires = None
    if isinstance(expires, datetime):
        expires = expires if expires.tzinfo else expires.replace(tzinfo=UTC)
        if expires <= _now() and not can_refresh:
            return _entry(service, name, AUTH_REQUIRED, f"{name} access expired. Reconnect it.")
    return _entry(service, name, CONNECTED, "Connected (not checked live).")


def check(db: Any, user_id: str) -> list[dict[str, Any]]:
    """Open Media first (checked live), then every other stored connection."""
    rows = db.table("integrations").select("*").eq("user_id", user_id).execute().data or []
    stored = [_stored(row) for row in rows if str(row.get("service_id") or "") not in HIDDEN]
    return [open_media(user_id), *sorted(stored, key=lambda e: e["name"])]
