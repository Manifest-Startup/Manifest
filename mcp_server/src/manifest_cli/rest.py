"""User-facing REST features that are not in GraphQL, as CLI commands.

Each entry is ``(group, name)`` → request. ``{placeholders}`` in the path become
positional arguments; ``body`` lists JSON body flags; ``body_input`` accepts a whole
JSON body via ``--input``. Anything else is reachable with ``manifest api``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BodyFlag:
    name: str  # JSON key
    type: str = "string"  # string | int | bool | list
    required: bool = False
    help: str = ""


@dataclass(frozen=True)
class RestCommand:
    group: str
    name: str  # "" for a single-command group
    method: str
    path: str
    help: str
    body: tuple[BodyFlag, ...] = ()
    body_input: bool = False
    upload: str | None = None  # multipart field name for a FILE positional
    destructive: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def command(self) -> str:
        return f"{self.group} {self.name}".strip()


REST_COMMANDS: tuple[RestCommand, ...] = (
    # API keys and clients (Account → API access)
    RestCommand(
        "keys", "clients", "GET", "/api/keys/clients", "List your API clients and their keys."
    ),
    RestCommand(
        "keys",
        "create-client",
        "POST",
        "/api/keys/clients",
        "Create an API client.",
        body=(BodyFlag("name", required=True, help="Client name"),),
    ),
    RestCommand(
        "keys",
        "delete-client",
        "DELETE",
        "/api/keys/clients/{client_id}",
        "Delete an API client and every key it has (needs a recent sign-in).",
        destructive=True,
    ),
    RestCommand(
        "keys",
        "create",
        "POST",
        "/api/keys/keys",
        "Create an API key; the secret is shown once (needs a recent sign-in).",
        body=(
            BodyFlag("client_id", required=True, help="API client id"),
            BodyFlag("name", help="Key name"),
            BodyFlag("expires_days", "int", help="Days until it expires (1-365)"),
            BodyFlag("scopes", "list", help="Permission scope (repeat for several)"),
        ),
    ),
    RestCommand(
        "keys",
        "rotate",
        "POST",
        "/api/keys/keys/rotate",
        "Rotate an API key; the old one keeps working for the overlap (needs a recent sign-in).",
        body=(
            BodyFlag("key_id", required=True, help="Key id to rotate"),
            BodyFlag("overlap_seconds", "int", help="Seconds the old key keeps working"),
        ),
        destructive=True,
    ),
    RestCommand(
        "keys",
        "revoke",
        "DELETE",
        "/api/keys/keys/{key_id}",
        "Revoke an API key (needs a recent sign-in).",
        destructive=True,
    ),
    RestCommand("keys", "tiers", "GET", "/api/keys/tiers", "Show API billing tiers and limits."),
    RestCommand("keys", "usage", "GET", "/api/keys/usage", "Show your API usage this period."),
    # Privacy and data-subject rights
    RestCommand("privacy", "consent", "GET", "/api/privacy/consent", "Show your privacy choices."),
    RestCommand(
        "privacy",
        "set-consent",
        "POST",
        "/api/privacy/consent",
        "Update your privacy choices.",
        body=(
            BodyFlag("analytics_enabled", "bool"),
            BodyFlag("communications_enabled", "bool"),
            BodyFlag("marketing_enabled", "bool"),
            BodyFlag("ai_training_enabled", "bool"),
            BodyFlag("cookies_enabled", "bool"),
            BodyFlag("do_not_sell_or_share", "bool"),
        ),
        body_input=True,
    ),
    RestCommand(
        "privacy",
        "withdraw-consent",
        "POST",
        "/api/privacy/consent/withdraw",
        "Withdraw consent for some or all purposes.",
        body=(
            BodyFlag("purposes", "list", help="Purpose to withdraw (repeat; none = all)"),
            BodyFlag("reason"),
        ),
        destructive=True,
    ),
    RestCommand(
        "dsar", "access", "GET", "/api/dsar/access", "Everything Manifest holds about you."
    ),
    RestCommand(
        "dsar", "export", "GET", "/api/dsar/portability", "Export your data (portable JSON)."
    ),
    RestCommand(
        "dsar",
        "rectify",
        "POST",
        "/api/dsar/rectify",
        "Correct your personal data (needs a recent sign-in).",
        body=(
            BodyFlag("full_name"),
            BodyFlag("first_name"),
            BodyFlag("last_name"),
            BodyFlag("email"),
        ),
    ),
    RestCommand(
        "dsar",
        "object",
        "POST",
        "/api/dsar/object",
        "Object to processing (analytics, communications, sale or sharing).",
        body=(
            BodyFlag("analytics_enabled", "bool"),
            BodyFlag("communications_enabled", "bool"),
            BodyFlag("do_not_sell_or_share", "bool"),
            BodyFlag("reason"),
        ),
    ),
    RestCommand(
        "dsar",
        "erase",
        "POST",
        "/api/dsar/erase",
        "Permanently erase your account and data (needs a recent sign-in).",
        body=(BodyFlag("confirm_email", required=True, help="Your account email, to confirm"),),
        destructive=True,
        extras={"acknowledge_irreversible": True},
    ),
    RestCommand(
        "dsar",
        "erase-certificate",
        "GET",
        "/api/dsar/erase/certificate",
        "Show the certificate for a completed erasure.",
    ),
    RestCommand(
        "dsar",
        "retention-exceptions",
        "GET",
        "/api/dsar/retention/exceptions",
        "Data kept despite an erasure request, and why.",
    ),
    # Account and integrations that are REST-only
    RestCommand(
        "upload-profile-picture",
        "",
        "POST",
        "/api/account/profile-picture",
        "Upload a profile picture (PNG, JPEG, WebP or GIF).",
        upload="file",
    ),
    RestCommand(
        "github-bootstrap",
        "",
        "POST",
        "/api/integrations/github/bootstrap",
        "Create a GitHub repository for an idea (needs the GitHub integration).",
        body=(
            BodyFlag("idea_id", required=True),
            BodyFlag("repo_name", required=True),
        ),
    ),
    RestCommand(
        "voice-capabilities",
        "",
        "GET",
        "/api/voice-agent/capabilities",
        "The voice assistant's command catalog.",
    ),
    RestCommand("trust-center", "", "GET", "/api/trust-center", "Manifest's security posture."),
)


def groups() -> dict[str, list[RestCommand]]:
    result: dict[str, list[RestCommand]] = {}
    for cmd in REST_COMMANDS:
        result.setdefault(cmd.group, []).append(cmd)
    return result


def path_params(cmd: RestCommand) -> list[str]:
    import re

    return re.findall(r"{(\w+)}", cmd.path)
