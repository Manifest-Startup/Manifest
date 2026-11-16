"""Link a Manifest account to Open Media ("Sign in with Open Media").

OAuth 2.1 authorization code + PKCE for a public client (no client secret).
Manifest's ``client_id`` is its Client ID Metadata Document URL.

The flow is stateless on the server: ``state`` is an HMAC-signed blob
(user id, nonce, expiry) and the PKCE ``code_verifier`` is derived from the
nonce with the session secret, so nothing is stored between ``/connect`` and
``/callback``. The callback only accepts a state minted for the signed-in user
(no login CSRF), within 10 minutes, once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from app.security.config import session_secret
from app.services.integrations.open_media import settings, store
from app.services.integrations.open_media.client import (
    OpenMediaError,
    get_client,
    person,
    require_enabled,
)
from app.services.shared.cache import cache_get, cache_set
from app.utils.logger import logger

STATE_TTL_SECONDS = 600


class OpenMediaLinkError(ValueError):
    """The callback could not complete (bad state, denied, exchange failed)."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _key(purpose: str) -> bytes:
    return hmac.new(session_secret().encode(), purpose.encode(), hashlib.sha256).digest()


def code_verifier(nonce: str) -> str:
    """43-character PKCE verifier, reproducible only with the server secret."""
    return _b64(hmac.new(_key("open-media-pkce"), nonce.encode(), hashlib.sha256).digest())


def code_challenge(verifier: str) -> str:
    return _b64(hashlib.sha256(verifier.encode()).digest())


def _sign_state(payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(_key("open-media-state"), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _read_state(state: str) -> dict[str, Any]:
    try:
        body, sig = state.split(".", 1)
        expected = _b64(hmac.new(_key("open-media-state"), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("signature")
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        raise OpenMediaLinkError("The Open Media sign-in link is invalid. Try again.") from None
    if not isinstance(payload, dict) or int(payload.get("e", 0)) < int(time.time()):
        raise OpenMediaLinkError("The Open Media sign-in link expired. Try again.")
    return payload


def authorize_url(user_id: str, *, login_hint: str | None = None) -> str:
    """Where ``GET /api/integrations/open-media/connect`` redirects the browser.

    ``login_hint`` (the person's Manifest email) pre-fills Open Media's sign-in page.
    """
    require_enabled()
    nonce = secrets.token_urlsafe(24)
    state = _sign_state({"u": str(user_id), "n": nonce, "e": int(time.time()) + STATE_TTL_SECONDS})
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.client_id(),
            "redirect_uri": settings.redirect_uri(),
            "scope": settings.OAUTH_SCOPE,
            "state": state,
            "code_challenge": code_challenge(code_verifier(nonce)),
            "code_challenge_method": "S256",
            **({"login_hint": login_hint} if login_hint else {}),
        }
    )
    return f"{settings.api_base()}/authorize?{query}"


def complete_link(user_id: str, *, code: str, state: str) -> dict[str, Any]:
    """Exchange the code, read the Open Media profile, store the encrypted link."""
    require_enabled()
    payload = _read_state(state)
    if str(payload.get("u")) != str(user_id):
        raise OpenMediaLinkError("This Open Media sign-in was started from another account.")
    nonce = str(payload.get("n") or "")
    used_key = f"open_media:oauth_nonce:{nonce}"
    if not nonce or cache_get(used_key):
        raise OpenMediaLinkError("This Open Media sign-in link was already used. Try again.")
    cache_set(used_key, True, STATE_TTL_SECONDS)

    client = get_client()
    try:
        tokens = client.token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.redirect_uri(),
                "code_verifier": code_verifier(nonce),
            }
        )
        access = str(tokens.get("access_token") or "")
        if not access:
            raise OpenMediaLinkError("Open Media did not return an access token.")
        profile = person(client.request("GET", "/v1/connected/me", token=access))
    except OpenMediaError as exc:
        logger.info("[open_media] link exchange failed: %s", exc.code or exc.status)
        raise OpenMediaLinkError("Open Media sign-in failed. Try again.") from None
    if not profile["id"] or not profile["handle"]:
        raise OpenMediaLinkError("Open Media did not return your profile.")

    metadata = store.save_link(
        str(user_id),
        om_user_id=profile["id"],
        handle=profile["handle"],
        access_token=access,
        refresh_token=tokens.get("refresh_token"),
        expires_in=tokens.get("expires_in"),
        profile=profile,
        scope=tokens.get("scope"),
    )
    return metadata


def link_status(user_id: str) -> dict[str, Any]:
    """What the Account card and feature gates need. Never includes tokens."""
    if not settings.enabled():
        return {"enabled": False, "linked": False}
    metadata = store.link_metadata(str(user_id))
    if not metadata:
        return {"enabled": True, "linked": False}
    return {
        "enabled": True,
        "linked": True,
        "needs_reconnect": bool(metadata.get("needs_reconnect")),
        "handle": metadata.get("handle"),
        "display_name": metadata.get("display_name"),
        "avatar_url": metadata.get("avatar_url"),
        "om_user_id": metadata.get("om_user_id"),
        "linked_at": metadata.get("linked_at"),
    }


def handle_for_user(user_id: str) -> str | None:
    """The founder's Open Media handle, or None if they have not linked (or must reconnect)."""
    if not user_id:
        return None
    metadata = store.link_metadata(str(user_id)) or {}
    if metadata.get("needs_reconnect"):
        return None
    handle = str(metadata.get("handle") or "").strip()
    return handle or None


def om_user_id_for(user_id: str) -> str | None:
    metadata = store.link_metadata(str(user_id)) or {}
    return str(metadata.get("om_user_id") or "") or None


def unlink(user_id: str) -> None:
    """Forget the link and its tokens. Open Media content stays in Open Media."""
    store.delete_link(str(user_id))
