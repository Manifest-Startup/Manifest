"""GraphQL types and mappers for third-party integrations and your own OpenAI key."""

from datetime import datetime

import strawberry


@strawberry.type
class Integration:
    integration_id: str
    user_id: str
    service_name: str
    service_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    connected_at: datetime
    metadata: str | None = None  # JSON string for additional service-specific data
    # True when the partner's own sign-in (OAuth) completed and Manifest holds
    # credentials; False for partners added by name or before OAuth is set up.
    linked: bool = False


@strawberry.type
class AiKeyStatus:
    """Bring-your-own-key status. ``source``: "user", "platform" or "none"."""

    configured: bool
    source: str
    last4: str | None = None


@strawberry.input
class ConnectIntegrationInput:
    service_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    metadata: str | None = None


@strawberry.type
class IntegrationConnection:
    """Result of starting a connection. ``status``: "connected", "already_connected"
    or "needs_browser" (open ``connectUrl`` to approve it on the provider's page)."""

    service_id: str
    status: str
    message: str
    connect_url: str | None = None


@strawberry.type
class IntegrationHealth:
    """Whether a connection works right now: verified (just used), connected (stored, not
    checked live), authentication_required, degraded or disconnected. Say ``detail``."""

    service: str
    name: str
    state: str
    detail: str
    checked_at: str
