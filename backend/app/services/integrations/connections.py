"""Start connecting a partner (integration) for someone, from the app or an agent.

Partners whose provider sign-in (OAuth) is set up must be approved in a browser,
so they get a link to Account → Integrations. Partners without a provider
sign-in are recorded straight away (no credentials), which is what the app's
Connect button does for them. Open Media is linked by signing in with it.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

OPEN_MEDIA_SERVICE_ID = "open_media"
GITHUB_SERVICE_ID = "github"
_SERVICE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
# Managed elsewhere: the OpenAI key lives in AI settings, never here.
_RESERVED = {"openai", "apollo"}

STATUS_CONNECTED = "connected"
STATUS_ALREADY_CONNECTED = "already_connected"
STATUS_NEEDS_BROWSER = "needs_browser"


@dataclass(frozen=True)
class ConnectionResult:
    service_id: str
    status: str
    message: str
    connect_url: str | None = None


def normalize_service_id(raw: str) -> str:
    service_id = (raw or "").strip().lower().replace(" ", "-")
    if not _SERVICE_ID_RE.match(service_id):
        raise ValueError(
            "serviceId must be 1-40 lowercase letters, digits, '-' or '_' (for example 'notion')."
        )
    if service_id in _RESERVED:
        raise ValueError(
            "Save your OpenAI or Apollo.io key in Account → AI settings, not as an integration."
        )
    return service_id


def display_name(service_id: str, name: str | None = None) -> str:
    cleaned = (name or "").strip()
    if cleaned:
        return cleaned[:80]
    if service_id == OPEN_MEDIA_SERVICE_ID:
        return "Open Media"
    if service_id == GITHUB_SERVICE_ID:
        return "GitHub"
    return " ".join(part.capitalize() for part in re.split(r"[-_]", service_id) if part)


def _is_connected(db: Any, user_id: str, service_id: str) -> bool:
    if service_id == GITHUB_SERVICE_ID:
        from app.services.integrations.github_account import github_identity

        return github_identity(user_id) is not None
    rows = (
        db.table("integrations")
        .select("integration_id")
        .eq("user_id", user_id)
        .eq("service_id", service_id)
        .execute()
    )
    return bool(rows.data)


def start_connection(
    db: Any,
    user_id: str,
    raw_service_id: str,
    *,
    oauth_ready: bool,
    site_origin: str,
    name: str | None = None,
) -> ConnectionResult:
    """Connect ``raw_service_id`` for ``user_id`` or say where to finish it."""
    service_id = normalize_service_id(raw_service_id)
    label = display_name(service_id, name)
    origin = site_origin.rstrip("/")

    if _is_connected(db, user_id, service_id):
        return ConnectionResult(
            service_id, STATUS_ALREADY_CONNECTED, f"{label} is already connected."
        )

    if service_id == OPEN_MEDIA_SERVICE_ID:
        return ConnectionResult(
            service_id,
            STATUS_NEEDS_BROWSER,
            "Open Media links when you sign in with it. Open the link to continue with Open Media.",
            f"{origin}/api/auth/open-media/start?next=/account",
        )

    if service_id == GITHUB_SERVICE_ID:
        # GitHub is only useful with a real token, so it is never recorded without one.
        return ConnectionResult(
            service_id,
            STATUS_NEEDS_BROWSER,
            "Open the link and choose Connect GitHub, or run `manifest github connect` on a "
            "computer already signed in to GitHub. It's one connection for the app, the CLI, "
            "agents and voice.",
            f"{origin}/account?focusIntegration=github",
        )

    if oauth_ready:
        return ConnectionResult(
            service_id,
            STATUS_NEEDS_BROWSER,
            f"{label} needs your approval on its own sign-in page. Open the link and choose Connect.",
            f"{origin}/account?focusIntegration={quote(service_id)}",
        )

    db.table("integrations").insert(
        {
            "integration_id": str(uuid.uuid4()),
            "user_id": user_id,
            "service_id": service_id,
            "service_name": label,
            "access_token": None,
            "refresh_token": None,
            "expires_at": None,
            "connected_at": datetime.now(UTC).isoformat(),
            "metadata": None,
        }
    ).execute()
    return ConnectionResult(
        service_id,
        STATUS_CONNECTED,
        f"{label} is now a connected partner. It shows under Key Partners on your canvases.",
    )


def connected_partner_names(user_id: str | None) -> list[str]:
    """Names of the partners ``user_id`` has connected (never credentials).

    Feeds canvas generation so Key Partners starts from real relationships.
    Best effort: an empty list when there is no database or no user.
    """
    if not user_id:
        return []
    try:
        from app.db.database import create_database_client

        rows = (
            create_database_client()
            .table("integrations")
            .select("service_id, service_name")
            .eq("user_id", user_id)
            .execute()
        ).data or []
    except Exception:  # noqa: BLE001 - generation must not fail on this lookup
        return []
    names: list[str] = []
    for row in rows:
        service_id = str(row.get("service_id") or "")
        if not service_id or service_id in _RESERVED:
            continue
        label = display_name(service_id, row.get("service_name"))
        if label not in names:
            names.append(label)
    return names


def partners_prompt_block(names: list[str]) -> str:
    """The prompt paragraph describing the founder's connected partners."""
    if not names:
        return "The founder has not connected any partners in Manifest yet."
    return (
        "Partners the founder already works with (connected in Manifest, so these are facts, "
        "not candidates): "
        + ", ".join(names)
        + ". List the relevant ones first under Key Partners as current partners, say what each "
        "contributes to this idea, and leave out any that don't fit it. Do not repeat them in "
        "suggestedServiceIds."
    )
