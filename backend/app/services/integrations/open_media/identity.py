"""Sign in to Manifest with Open Media ("Continue with Open Media").

Open Media is Manifest's only identity provider: OAuth 2.1 authorization code +
PKCE for a public client (no client secret). Manifest's ``client_id`` is its
Client ID Metadata Document URL.

The flow keeps no server-side state between ``/start`` and ``/callback``:

- ``state`` is an HMAC-signed blob: nonce, safe ``next`` path, the guest user to
  merge (if a guest started it), the signed-in user to re-link (if any), expiry.
- The PKCE ``code_verifier`` is derived from the nonce with the session secret.
- The nonce is also set in a short-lived, signed, HttpOnly cookie, and the
  callback only accepts a state whose nonce matches that cookie (no login CSRF),
  within 10 minutes, once.

The callback then finds the Manifest user: by the stored Open Media id, else the
signed-in user who started a reconnect, else a non-guest account whose email
matches Open Media's *verified* email (auto-link), else a new full account.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.db.database import get_db_connection
from app.security.config import session_secret
from app.services.integrations.open_media import settings, store
from app.services.integrations.open_media.client import (
    OpenMediaError,
    get_client,
    person,
    pick,
)
from app.services.shared.cache import cache_get, cache_set
from app.utils.logger import logger

STATE_TTL_SECONDS = 600


class OpenMediaLinkError(ValueError):
    """The sign-in could not complete. ``str(exc)`` is safe to show; ``code`` goes in URLs."""

    def __init__(self, message: str, code: str = "failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OpenMediaAccount:
    """The person behind an Open Media access token (``GET /v1/connected/me``)."""

    om_user_id: str
    handle: str
    display_name: str
    avatar_url: str | None
    email: str
    email_verified: bool
    has_profile: bool

    @classmethod
    def from_me(cls, record: Any) -> OpenMediaAccount:
        profile = person(record)
        raw_email = pick(record, "email", default="")
        email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
        has_profile = pick(record, "has_profile", "hasProfile")
        return cls(
            om_user_id=profile["id"],
            handle=profile["handle"],
            display_name=profile["display_name"],
            avatar_url=profile["avatar_url"],
            email=email if "@" in email else "",
            email_verified=pick(record, "email_verified", "emailVerified") is True,
            has_profile=bool(profile["handle"]) if has_profile is None else bool(has_profile),
        )


@dataclass(frozen=True)
class SignInResult:
    user_id: str
    email: str
    #: how the Manifest user was found: ``open_media_id``, ``session``, ``email`` or ``new``
    matched_by: str
    next_path: str
    guest_user_id: str | None
    account: OpenMediaAccount


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _key(purpose: str) -> bytes:
    return hmac.new(session_secret().encode(), purpose.encode(), hashlib.sha256).digest()


def _mac(purpose: str, text: str) -> str:
    return _b64(hmac.new(_key(purpose), text.encode(), hashlib.sha256).digest())


def code_verifier(nonce: str) -> str:
    """43-character PKCE verifier, reproducible only with the server secret."""
    return _mac("open-media-pkce", nonce)


def code_challenge(verifier: str) -> str:
    return _b64(hashlib.sha256(verifier.encode()).digest())


def nonce_cookie_value(nonce: str) -> str:
    """The signed nonce stored in the browser's sign-in cookie."""
    return f"{nonce}.{_mac('open-media-nonce-cookie', nonce)}"


def _nonce_from_cookie(value: str | None) -> str | None:
    nonce, _, sig = (value or "").rpartition(".")
    if not nonce or not hmac.compare_digest(sig, _mac("open-media-nonce-cookie", nonce)):
        return None
    return nonce


def _sign_state(payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_mac('open-media-state', body)}"


def _read_state(state: str) -> dict[str, Any]:
    try:
        body, sig = state.split(".", 1)
        if not hmac.compare_digest(sig, _mac("open-media-state", body)):
            raise ValueError("signature")
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        raise OpenMediaLinkError(
            "The Open Media sign-in link is invalid. Try again.", "invalid_state"
        ) from None
    if not isinstance(payload, dict) or int(payload.get("e", 0)) < int(time.time()):
        raise OpenMediaLinkError("The Open Media sign-in link expired. Try again.", "expired")
    return payload


def authorize_url(
    *,
    next_path: str = "/ideas",
    guest_user_id: str | None = None,
    user_id: str | None = None,
    login_hint: str | None = None,
) -> tuple[str, str]:
    """Open Media ``/authorize`` URL for ``GET /api/auth/open-media/start``, and its nonce.

    ``next_path`` must already be a safe same-origin path. ``guest_user_id`` is the
    guest workspace to merge after sign-in; ``user_id`` is a signed-in account that
    is reconnecting. ``login_hint`` pre-fills Open Media's sign-in page.
    """
    nonce = secrets.token_urlsafe(24)
    payload: dict[str, Any] = {
        "n": nonce,
        "x": next_path,
        "e": int(time.time()) + STATE_TTL_SECONDS,
    }
    if guest_user_id:
        payload["g"] = str(guest_user_id)
    if user_id:
        payload["u"] = str(user_id)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.client_id(),
            "redirect_uri": settings.redirect_uri(),
            "scope": settings.OAUTH_SCOPE,
            "state": _sign_state(payload),
            "code_challenge": code_challenge(code_verifier(nonce)),
            "code_challenge_method": "S256",
            **({"login_hint": login_hint} if login_hint else {}),
        }
    )
    return f"{settings.api_base()}/authorize?{query}", nonce


def complete_sign_in(
    *, code: str, state: str, nonce_cookie: str | None, session_user_id: str | None
) -> SignInResult:
    """Verify the state, exchange the code, find or create the user, store the link.

    ``session_user_id`` is whoever the browser is signed in as right now (a guest,
    a full account, or None). It only matters when the state names that same user.
    """
    payload = _read_state(state)
    nonce = str(payload.get("n") or "")
    cookie_nonce = _nonce_from_cookie(nonce_cookie)
    if not nonce or not cookie_nonce or not hmac.compare_digest(nonce, cookie_nonce):
        raise OpenMediaLinkError(
            "This sign-in was started in another browser or tab. Try again.", "invalid_state"
        )
    used_key = f"open_media:oauth_nonce:{nonce}"
    if cache_get(used_key):
        raise OpenMediaLinkError(
            "This Open Media sign-in link was already used. Try again.", "replayed"
        )
    cache_set(used_key, True, STATE_TTL_SECONDS)

    tokens, account = _exchange(code, nonce)
    reconnecting = str(payload.get("u") or "") or None
    bound_user_id = reconnecting if reconnecting and reconnecting == session_user_id else None
    user_id, email, matched_by = _resolve_user(account, bound_user_id)

    store.save_link(
        user_id,
        om_user_id=account.om_user_id,
        handle=account.handle,
        access_token=str(tokens["access_token"]),
        refresh_token=tokens.get("refresh_token"),
        expires_in=tokens.get("expires_in"),
        profile={"display_name": account.display_name, "avatar_url": account.avatar_url},
        scope=tokens.get("scope"),
    )
    guest = str(payload.get("g") or "") or None
    logger.info("[open_media] signed in user=%s matched_by=%s", user_id, matched_by)
    return SignInResult(
        user_id=user_id,
        email=email,
        matched_by=matched_by,
        next_path=str(payload.get("x") or "/ideas"),
        guest_user_id=guest if guest and guest == session_user_id else None,
        account=account,
    )


def _exchange(code: str, nonce: str) -> tuple[dict[str, Any], OpenMediaAccount]:
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
        account = OpenMediaAccount.from_me(client.request("GET", "/v1/connected/me", token=access))
    except OpenMediaError as exc:
        logger.info("[open_media] sign-in exchange failed: %s", exc.code or exc.status)
        raise OpenMediaLinkError("Open Media sign-in failed. Try again.") from None
    if not account.om_user_id:
        raise OpenMediaLinkError("Open Media did not return your account.")
    return tokens, account


# -- finding the Manifest user ---------------------------------------------


def _value(row: Any, name: str) -> Any:
    if row is None:
        return None
    return row[name] if isinstance(row, dict) else row[0]


def _resolve_user(account: OpenMediaAccount, bound_user_id: str | None) -> tuple[str, str, str]:
    """``(user_id, email, matched_by)`` for this Open Media account. Creates at most one row."""
    with get_db_connection() as conn, conn.cursor() as cur:
        linked = _user_linked_to(cur, account.om_user_id)
        if linked and bound_user_id and linked != bound_user_id:
            raise OpenMediaLinkError(
                "That Open Media account is already linked to another Manifest account.",
                "linked_elsewhere",
            )
        if linked or bound_user_id:
            user_id = str(linked or bound_user_id)
            row = _load_user(cur, user_id)
            if row is None:
                raise OpenMediaLinkError("Your Manifest account was not found.")
            if row.get("disabled_at") is not None:
                raise OpenMediaLinkError("This Manifest account is disabled.", "account_disabled")
            return (
                user_id,
                str(row.get("email") or account.email),
                ("open_media_id" if linked else "session"),
            )

        if not account.email:
            raise OpenMediaLinkError(
                "Your Open Media account has no email address. Add one in Open Media and try again.",
                "no_email",
            )
        if not account.email_verified:
            raise OpenMediaLinkError(
                "Confirm your email address in Open Media, then continue again.",
                "unverified_email",
            )

        existing = _user_by_email(cur, account.email)
        if existing is not None:
            user_id = str(existing["user_id"])
            if existing.get("disabled_at") is not None:
                raise OpenMediaLinkError("This Manifest account is disabled.", "account_disabled")
            other = _linked_om_user_id(cur, user_id)
            if other and other != account.om_user_id:
                raise OpenMediaLinkError(
                    "Your Manifest account is linked to a different Open Media account.",
                    "linked_elsewhere",
                )
            return user_id, account.email, "email"

        user_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO users (user_id, email, auth_provider, created_at)
            VALUES (%s, %s, 'open_media', NOW())
            """,
            (user_id, account.email),
        )
        conn.commit()
        return user_id, account.email, "new"


def _user_linked_to(cur, om_user_id: str) -> str | None:
    """The full (non-guest) Manifest account linked to this Open Media id, oldest first."""
    cur.execute(
        """
        SELECT i.user_id
        FROM integrations i JOIN users u ON u.user_id = i.user_id
        WHERE i.service_id = %s
          AND (CASE WHEN i.service_id = %s THEN i.metadata::jsonb ->> 'om_user_id' END) = %s
          AND COALESCE(u.is_guest, FALSE) = FALSE
        ORDER BY i.connected_at ASC
        LIMIT 1
        """,
        (store.SERVICE_ID, store.SERVICE_ID, om_user_id),
    )
    found = _value(cur.fetchone(), "user_id")
    return str(found) if found else None


def _linked_om_user_id(cur, user_id: str) -> str | None:
    cur.execute(
        "SELECT metadata FROM integrations WHERE user_id = %s AND service_id = %s",
        (user_id, store.SERVICE_ID),
    )
    row = cur.fetchone()
    if row is None:
        return None
    metadata = store._parse_metadata(_value(row, "metadata"))
    return str(metadata.get("om_user_id") or "") or None


def _load_user(cur, user_id: str) -> dict[str, Any] | None:
    cur.execute("SELECT user_id, email, disabled_at FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    return dict(row) if row is not None else None


def _user_by_email(cur, email: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT user_id, email, disabled_at FROM users
        WHERE lower(email) = lower(%s) AND COALESCE(is_guest, FALSE) = FALSE
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (email,),
    )
    row = cur.fetchone()
    return dict(row) if row is not None else None


def link_status(user_id: str) -> dict[str, Any]:
    """What the Account card and feature gates need. Never includes tokens.

    ``enabled`` says whether Messages and Pitch Shorts run on this server; the link
    itself exists for every account that signed in with Open Media.
    """
    enabled = settings.enabled()
    metadata = store.link_metadata(str(user_id))
    if not metadata:
        return {"enabled": enabled, "linked": False}
    return {
        "enabled": enabled,
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
