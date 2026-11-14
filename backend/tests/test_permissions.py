"""RBAC catalog regression tests for `app.security.permissions`.

Covers the guest try-before-signup contract documented in `AGENTS.md`:
guests must have the full own-workspace surface (so the founder workspace
renders end-to-end) but must NOT have any social or admin permission. The
social mutations are also gated at the resolver layer by
`_require_full_account`, but the RBAC check is the transport-level gate
and must stay correct on its own (defense in depth).

These assertions are pure dict/set membership — no DB, no FastAPI.
"""
from __future__ import annotations

from app.security.permissions import (
    GUEST_PERMISSIONS,
    ROLE_PERMISSIONS,
    USER_PERMISSIONS,
    Principal,
)


def _guest_principal() -> Principal:
    return Principal(
        user_id="guest+test",
        role="guest",
        is_guest=True,
        permissions=set(ROLE_PERMISSIONS["guest"]),
    )


def test_guest_role_resolves_to_workspace_permissions():
    assert ROLE_PERMISSIONS["guest"] is GUEST_PERMISSIONS
    assert GUEST_PERMISSIONS, "guest role must not be empty — guests need the workspace surface"


def test_guest_has_workspace_read_write_permissions():
    """Every FIELD_PERMISSIONS string the founder workspace touches on first render."""
    principal = _guest_principal()
    for perm in (
        "ideas.read",
        "ideas.write",
        "documents.read",
        "documents.write",
        "account.read",
        "account.write",
        "sessions.manage",
    ):
        assert principal.has(perm), f"guest role is missing required workspace permission: {perm}"


def test_guest_lacks_social_admin_and_mfa_permissions():
    """Defense-in-depth: even if `_require_full_account` ever regresses, RBAC still blocks."""
    principal = _guest_principal()
    for perm in (
        # MFA self-service — guests have no MFA surface.
        "mfa.manage",
        # API key issuance is account-only.
        "api_keys.manage",
        # Admin surfaces.
        "admin.users.read",
        "admin.users.write",
        "admin.users.impersonate",
        "admin.lockouts.clear",
        "admin.audit.read",
        "admin.sso.manage",
        "admin.scim.read",
        "admin.scim.write",
        "admin.api_keys.revoke_any",
        # Workspace owner controls (guests are not owners).
        "workspace.manage",
        "workspace.billing",
        "workspace.members.invite",
        "workspace.members.remove",
        "workspace.members.role",
    ):
        assert not principal.has(perm), f"guest role must NOT grant {perm}"


def test_member_role_unchanged_by_guest_widening():
    """Regression guard: the member surface is the authoritative non-guest user set
    and must not drift when we expand the guest set."""
    # Member role must still be the catalog USER_PERMISSIONS (no shared mutation).
    assert ROLE_PERMISSIONS["member"] is USER_PERMISSIONS
    assert ROLE_PERMISSIONS["user"] is USER_PERMISSIONS  # backwards-compat alias

    # Guest must be a strict subset of member — guests never get a permission
    # that members don't also have. The opposite (member ⊃ guest) is what
    # lets the merge_guest_workspace flow work seamlessly.
    assert GUEST_PERMISSIONS.issubset(USER_PERMISSIONS), (
        "guest permissions must be a subset of member permissions; "
        f"extra: {GUEST_PERMISSIONS - USER_PERMISSIONS}"
    )
