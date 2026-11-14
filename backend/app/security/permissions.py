"""Centralised RBAC permission catalog (SEC-028).

Why a flat catalog instead of a roles table:
- The current platform has exactly two principal classes (regular user
  and admin) and one delegated principal (API client). A full RBAC table
  would over-engineer for the present blast radius.
- This module makes adding finer roles trivial: extend ``ROLE_PERMISSIONS``
  and ``resolve_permissions(user_row)``.

Permissions are dotted strings (``resource.action``). Adding a new
permission is a one-line change here plus a ``Depends(require_permission(...))``
on the route. The catalog is the single source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.auth.current_user import require_user_id
from app.db.database import get_db_connection
from app.utils.logger import logger
from fastapi import Depends, HTTPException, Request

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

# Generic user permissions — granted to any authenticated, non-guest user.
USER_PERMISSIONS: set[str] = {
    "ideas.read",
    "ideas.write",
    "documents.read",
    "documents.write",
    "account.read",
    "account.write",
    "api_keys.manage",
    "sessions.manage",
    "mfa.manage",
}

# Admin permissions — granted only to users with users.is_admin = TRUE.
# Admin actions also require recent step-up auth (see security.step_up).
ADMIN_PERMISSIONS: set[str] = {
    "admin.users.read",
    "admin.users.write",
    "admin.users.impersonate",
    "admin.lockouts.clear",
    "admin.audit.read",
    "admin.sso.manage",
    "admin.scim.read",
    "admin.scim.write",
    "admin.api_keys.revoke_any",
    # Cross-user cost + agent-run + production-test analytics.
    # Read-only by design; cap-control changes still go through the
    # per-user account.write surface.
    "admin.cost.read",
    # AI-driven voice-platform testing. Read = view test runs +
    # stats; write = trigger new test cases against the platform
    # (each test run spends LLM tokens, hence the separate
    # write permission).
    "admin.voice_testing.read",
    "admin.voice_testing.write",
}

# Read-only subset for viewer roles (e.g. shared workspace consumers).
VIEWER_PERMISSIONS: set[str] = {
    "ideas.read",
    "documents.read",
    "account.read",
}

# Try-before-signup guest permissions. Guests get the full own-workspace
# surface (ideas + documents read/write, account read/write, single-session
# self-service) so they can build, save, generate, and upgrade. The cross-
# user social actions they must NOT do (publish, invest, follow, messaging,
# collaborator invite, MFA) are independently blocked at the resolver layer
# via `_require_full_account` in `backend/app/graphql/schema.py` — see
# `AGENTS.md` § "Guest try-before-signup" for the canonical contract.
# `api_keys.manage` and every `admin.*` permission stay out by omission.
GUEST_PERMISSIONS: set[str] = {
    "ideas.read",
    "ideas.write",
    "documents.read",
    "documents.write",
    "account.read",
    "account.write",
    "sessions.manage",
}

# Service principals (machine-to-machine via API keys) get a tightly
# scoped slice of the user permission set, with destructive admin
# actions explicitly excluded by API_KEY_FORBIDDEN below.
SERVICE_PERMISSIONS: set[str] = {
    "ideas.read",
    "ideas.write",
    "documents.read",
    "documents.write",
}

# Owners are the workspace-level superuser — everything a member can do
# plus the privileged member/billing controls. We keep "admin" reserved
# for platform staff (cross-tenant); "owner" is per-tenant.
OWNER_PERMISSIONS: set[str] = USER_PERMISSIONS | {
    "workspace.manage",
    "workspace.billing",
    "workspace.members.invite",
    "workspace.members.remove",
    "workspace.members.role",
}

# Canonical role taxonomy (SEC-028). Order matters for the docs UI but
# not for enforcement — every check is membership-based.
ROLE_PERMISSIONS = {
    "guest": GUEST_PERMISSIONS,  # own-workspace only; social/admin gated elsewhere
    "viewer": VIEWER_PERMISSIONS,
    "member": USER_PERMISSIONS,
    "user": USER_PERMISSIONS,  # backwards-compat alias for "member"
    "owner": OWNER_PERMISSIONS,
    "admin": USER_PERMISSIONS | ADMIN_PERMISSIONS | OWNER_PERMISSIONS,
    "service": SERVICE_PERMISSIONS,
}

# Roles that may be assigned by an admin. "admin" itself is not in this
# set on purpose — promoting to platform admin is a separate, more
# tightly audited path.
ASSIGNABLE_ROLES = {"viewer", "member", "owner"}

# Permissions never granted to API key clients regardless of scope, because
# they would let a leaked key escalate to UI-only operations.
API_KEY_FORBIDDEN: set[str] = {
    "admin.users.impersonate",
    "admin.users.write",
    "mfa.manage",
    "sessions.manage",
}


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    is_admin: bool = False
    is_guest: bool = False
    permissions: set[str] = field(default_factory=set)
    sso_tenant_id: str | None = None

    def has(self, perm: str) -> bool:
        return perm in self.permissions


def _load_user_row(user_id: str) -> dict | None:
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT user_id,
                           COALESCE(is_admin, FALSE) AS is_admin,
                           COALESCE(is_guest, FALSE) AS is_guest,
                           COALESCE(role, '') AS role,
                           sso_tenant_id
                    FROM users WHERE user_id = %s
                    """,
                (user_id,),
            )
            return cur.fetchone()
    except Exception as exc:
        logger.warning("[permissions] load_user_row failed for %s: %s", user_id, exc)
        return None


def resolve_principal(user_id: str) -> Principal:
    row = _load_user_row(user_id) or {}
    is_admin = bool(row.get("is_admin"))
    is_guest = bool(row.get("is_guest"))
    explicit_role = (row.get("role") or "").strip().lower()
    if is_admin:
        role = "admin"
    elif is_guest:
        role = "guest"
    elif explicit_role in ROLE_PERMISSIONS:
        role = explicit_role
    else:
        role = "member"  # safer default than legacy "user"
    perms = set(ROLE_PERMISSIONS.get(role, set()))
    return Principal(
        user_id=user_id,
        role=role,
        is_admin=is_admin,
        is_guest=is_guest,
        permissions=perms,
        sso_tenant_id=str(row.get("sso_tenant_id")) if row.get("sso_tenant_id") else None,
    )


def get_principal(request: Request, user_id: str = Depends(require_user_id)) -> Principal:
    """FastAPI dependency: resolve the authenticated principal."""
    return resolve_principal(user_id)


def require_permission(permission: str):
    """Return a FastAPI dependency that enforces ``permission``."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.has(permission):
            return principal
        logger.info(
            "[permissions] denied user=%s role=%s permission=%s",
            principal.user_id,
            principal.role,
            permission,
        )
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return _dep


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    """Convenience dependency: caller must be an admin (and pass step-up upstream).

    Admin accounts MUST have MFA enrolled (SEC-029): a stolen admin
    password alone must never be sufficient to access admin surfaces. We
    enforce this here so it applies uniformly to every admin route, even
    if a future route author forgets to wire step-up explicitly.
    """
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        from app.services.identity.totp_mfa import get_user_mfa_status

        if not get_user_mfa_status(principal.user_id).get("enabled"):
            raise HTTPException(
                status_code=403,
                detail="MFA enrolment is required for admin accounts.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[permissions] admin MFA check failed: %s", exc)
        # Fail closed if we cannot determine MFA status for an admin.
        raise HTTPException(status_code=503, detail="Admin MFA status unavailable") from exc
    return principal


def filter_api_key_scopes(scopes: Iterable[str]) -> list[str]:
    """Drop any API-key scope that maps to a UI-only or sensitive permission."""
    return [s for s in scopes if s not in API_KEY_FORBIDDEN]
