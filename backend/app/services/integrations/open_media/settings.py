"""Open Media settings, read from the environment on every call (cheap, test-friendly)."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

DEFAULT_API_BASE = "https://api.openmedia.site"
DEFAULT_CLIENT_ID = "https://manifeststartup.com/oauth/open-media-client.json"
DEFAULT_REDIRECT_URI = "https://manifeststartup.com/api/auth/open-media/callback"
OAUTH_SCOPE = "account"
APP_TAG = "manifest"

_TRUE = {"1", "true", "yes", "on"}


def enabled() -> bool:
    """Messages and Pitch Shorts are hidden unless ``OPEN_MEDIA_ENABLED`` is truthy."""
    return (os.getenv("OPEN_MEDIA_ENABLED") or "").strip().lower() in _TRUE


def api_base() -> str:
    return (os.getenv("OPEN_MEDIA_API_BASE") or DEFAULT_API_BASE).strip().rstrip("/")


def client_id() -> str:
    return (os.getenv("OPEN_MEDIA_CLIENT_ID") or DEFAULT_CLIENT_ID).strip()


def redirect_uri() -> str:
    """Must match ``redirect_uris`` in the client metadata document.

    ``OPEN_MEDIA_REDIRECT_URI`` exists only for a local Open Media stack.
    """
    return (os.getenv("OPEN_MEDIA_REDIRECT_URI") or DEFAULT_REDIRECT_URI).strip()


def webhook_secret() -> str:
    return (os.getenv("OPEN_MEDIA_WEBHOOK_SECRET") or "").strip()


def app_origin() -> str:
    """Public Manifest origin for ``context.url`` links.

    Open Media only accepts https URLs on manifeststartup.com (or a subdomain),
    so a local redirect URI still links to the production site.
    """
    parts = urlsplit(redirect_uri())
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and (
        host == "manifeststartup.com" or host.endswith(".manifeststartup.com")
    ):
        return f"https://{parts.netloc}"
    return "https://manifeststartup.com"


def clip_url(reel_id: str) -> str:
    return f"{app_origin()}/pitch-reels?clip={reel_id}"
