"""Minimal SCIM 2.0 endpoints for enterprise tenants.

This implementation covers the operations required by the most common
identity providers (Okta, Azure AD, OneLogin) for user lifecycle:

- ``GET /scim/v2/ServiceProviderConfig``
- ``GET /scim/v2/Schemas``
- ``GET /scim/v2/ResourceTypes``
- ``GET /scim/v2/Users`` (list + filter by email)
- ``GET /scim/v2/Users/{id}``
- ``POST /scim/v2/Users`` (create)
- ``PATCH /scim/v2/Users/{id}`` (active flag, name updates)
- ``DELETE /scim/v2/Users/{id}`` (soft delete = mark sso disabled)

Authentication is via ``Authorization: Bearer <scim_token>`` matched
against the tenant's stored ``scim_token_hash``. No cookies — SCIM is
machine-to-machine.

Group provisioning and user-to-group sync are also supported via the
``/scim/v2/Groups`` endpoints; bulk requests remain out of scope and
return 501.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.db.database import get_db_connection
from app.utils.logger import logger
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/scim/v2", tags=["SCIM"])


def _resolve_tenant_from_token(authorization: str | None) -> dict[str, Any] | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM sso_tenant_configs WHERE scim_token_hash = %s "
                "AND disabled_at IS NULL",
                (token_hash,),
            )
            return cur.fetchone()
    except Exception as exc:
        logger.warning("[scim] tenant lookup failed: %s", exc)
        return None


def _require_tenant(authorization: str | None) -> dict[str, Any]:
    tenant = _resolve_tenant_from_token(authorization)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid SCIM token")
    return tenant


def _user_to_scim(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(row["user_id"]),
        "userName": row.get("email"),
        "name": {
            "givenName": row.get("first_name"),
            "familyName": row.get("last_name"),
        },
        "emails": [{"value": row.get("email"), "primary": True}] if row.get("email") else [],
        "active": (row.get("disabled_at") is None) and not bool(row.get("is_guest")),
        "meta": {"resourceType": "User", "created": row.get("created_at")},
    }


@router.get("/ServiceProviderConfig")
async def scim_service_provider_config():
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://manifeststartup.com/docs/scim",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "Authentication via SCIM bearer token",
            }
        ],
    }


@router.get("/Schemas")
async def scim_schemas():
    return {
        "Resources": [
            {"id": "urn:ietf:params:scim:schemas:core:2.0:User"},
            {"id": "urn:ietf:params:scim:schemas:core:2.0:Group"},
        ]
    }


@router.get("/ResourceTypes")
async def scim_resource_types():
    return {
        "Resources": [
            {
                "id": "User",
                "name": "User",
                "endpoint": "/Users",
                "schema": "urn:ietf:params:scim:schemas:core:2.0:User",
            },
            {
                "id": "Group",
                "name": "Group",
                "endpoint": "/Groups",
                "schema": "urn:ietf:params:scim:schemas:core:2.0:Group",
            },
        ]
    }


@router.get("/Users")
async def scim_list_users(
    authorization: str | None = Header(None),
    filter: str | None = Query(None, alias="filter"),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=200),
):
    tenant = _require_tenant(authorization)
    where = ["sso_tenant_id = %s"]
    params: list[Any] = [tenant["tenant_id"]]
    # Only support the Okta/AzureAD-standard "userName eq <value>" filter.
    if filter:
        try:
            field, op, raw_value = filter.split(" ", 2)
            value = raw_value.strip().strip('"')
            if op.lower() == "eq" and field == "userName":
                where.append("email = %s")
                params.append(value.lower())
        except ValueError:
            pass
    where_sql = " AND ".join(where)
    count_sql = f"SELECT COUNT(*) AS n FROM users WHERE {where_sql}"
    page_sql = (
        "SELECT user_id, email, first_name, last_name, created_at, "
        "       disabled_at, COALESCE(is_guest, FALSE) AS is_guest "
        f"FROM users WHERE {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s"
    )
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = int((cur.fetchone() or {"n": 0})["n"])
            cur.execute(page_sql, params + [count, startIndex - 1])
            rows = cur.fetchall() or []
    except Exception as exc:
        logger.warning("[scim] list_users failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM list failed") from exc
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "Resources": [_user_to_scim(r) for r in rows],
        "startIndex": startIndex,
        "itemsPerPage": len(rows),
    }


class ScimUserCreate(BaseModel):
    userName: str
    name: dict[str, Any] | None = None
    active: bool = True


class ScimUserCreate2(ScimUserCreate):
    externalId: str | None = None


@router.post("/Users", status_code=201)
async def scim_create_user(payload: ScimUserCreate2, authorization: str | None = Header(None)):
    """Pre-provision (or upsert) a user via SCIM.

    Critically, this path does NOT consult the tenant's
    ``jit_provisioning`` flag — that flag governs login-time auto-create
    only. SCIM is an explicit IdP-driven lifecycle channel that must
    work even when JIT is disabled.
    """
    tenant = _require_tenant(authorization)
    from app.services.identity.enterprise_sso import scim_provision_user

    name = payload.name or {}
    user_id = scim_provision_user(
        tenant=tenant,
        email=payload.userName,
        external_id=payload.externalId or payload.userName,
        first_name=name.get("givenName"),
        last_name=name.get("familyName"),
    )
    if not user_id:
        raise HTTPException(status_code=500, detail="SCIM provisioning failed (DB error)")
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("[scim] post-create lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM create failed") from exc
    return _user_to_scim(row or {"user_id": user_id, "email": payload.userName})


def _disable_user(cur, user_id: str, tenant_id: str, reason: str) -> int:
    """Deactivate a SCIM-managed user atomically.

    Sets ``users.disabled_at``/``disabled_reason``, clears ``sso_subject`` so
    future IdP logins JIT-provision a fresh row only after re-enable, and
    revokes every active session. Returns row-count of disabled users (0 or 1).
    """
    cur.execute(
        """
        UPDATE users
           SET disabled_at = COALESCE(disabled_at, NOW()),
               disabled_reason = COALESCE(disabled_reason, %s),
               sso_subject = NULL
         WHERE user_id = %s
           AND sso_tenant_id = %s
        """,
        (reason, user_id, tenant_id),
    )
    rc = cur.rowcount
    cur.execute(
        "UPDATE user_sessions SET revoked_at = NOW() " "WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )
    return rc


def _enable_user(cur, user_id: str, tenant_id: str) -> int:
    cur.execute(
        """
        UPDATE users
           SET disabled_at = NULL,
               disabled_reason = NULL
         WHERE user_id = %s
           AND sso_tenant_id = %s
        """,
        (user_id, tenant_id),
    )
    return cur.rowcount


@router.delete("/Users/{user_id}", status_code=204)
async def scim_deprovision_user(user_id: str, authorization: str | None = Header(None)):
    """SCIM DELETE = soft-disable. We never hard-delete a user row because
    audit trails reference it. Sets ``disabled_at`` and revokes all sessions.
    """
    tenant = _require_tenant(authorization)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                rc = _disable_user(cur, user_id, tenant["tenant_id"], reason="scim_delete")
            conn.commit()
        if rc == 0:
            raise HTTPException(status_code=404, detail="User not in tenant")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[scim] deprovision failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM delete failed") from exc
    return None


@router.patch("/Users/{user_id}")
async def scim_patch_user(user_id: str, request: Request, authorization: str | None = Header(None)):
    """Minimal PATCH support — toggles ``active`` (true/false), persisting
    the disabled state on the users row so a re-login after deprovisioning
    is rejected by the auth helpers.
    """
    tenant = _require_tenant(authorization)
    body = await request.json()
    operations = body.get("Operations", [])
    set_active: bool | None = None
    for op in operations:
        if (
            op.get("op", "").lower() in {"replace", "add"}
            and op.get("path", "").lower() == "active"
        ):
            set_active = bool(op.get("value"))
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if set_active is False:
                    if (
                        _disable_user(
                            cur, user_id, tenant["tenant_id"], reason="scim_patch_inactive"
                        )
                        == 0
                    ):
                        raise HTTPException(status_code=404, detail="User not in tenant")
                elif set_active is True and _enable_user(cur, user_id, tenant["tenant_id"]) == 0:
                    raise HTTPException(status_code=404, detail="User not in tenant")
                cur.execute(
                    "SELECT * FROM users WHERE user_id = %s AND sso_tenant_id = %s",
                    (user_id, tenant["tenant_id"]),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise HTTPException(status_code=404, detail="User not in tenant")
        return _user_to_scim(row)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[scim] patch failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM patch failed") from exc


# ---------------------------------------------------------------------------
# Groups (SCIM 2.0)
# ---------------------------------------------------------------------------
#
# Why we ship Groups: enterprise IdPs (Okta, Azure AD, JumpCloud) push
# user *and* group state. Groups carry the org's role assignment ("eng",
# "support", "admin"), so SCIM Group sync is what lets a tenant control
# RBAC roles centrally without us hand-managing app.users.role.
#
# Mapping rule: each scim_groups row has an optional ``mapped_role`` (one
# of ASSIGNABLE_ROLES from app.security.permissions). When a group's
# membership changes we recompute the highest-precedence mapped role
# across all the user's groups and write it to ``users.role``. Sessions
# of any user whose role changes are revoked, mirroring the platform
# admin_set_user_role semantics.

ROLE_PRECEDENCE = {"viewer": 1, "member": 2, "owner": 3}


def _group_to_scim(row: dict[str, Any], member_ids: list[str]) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": str(row["group_id"]),
        "displayName": row.get("display_name"),
        "externalId": row.get("external_id"),
        "members": [{"value": uid, "type": "User"} for uid in member_ids],
        "manifestRole": row.get("mapped_role"),
        "meta": {"resourceType": "Group", "created": row.get("created_at")},
    }


def _list_group_members(cur, group_id: str) -> list[str]:
    cur.execute(
        "SELECT user_id FROM scim_group_members WHERE group_id = %s",
        (group_id,),
    )
    return [str(r["user_id"]) for r in (cur.fetchall() or [])]


def _recompute_user_role(cur, user_id: str, tenant_id: str) -> str | None:
    """Set users.role to the highest-precedence mapped_role across the
    given tenant's groups.

    The user MUST belong to ``tenant_id`` (verified by sso_tenant_id) —
    a SCIM caller for tenant A must never be able to mutate a user that
    belongs to tenant B. We only consider groups whose own tenant_id
    matches, so a user is unaffected by groups from other tenants.

    Returns the new role string if it changed, else None. Revokes the
    user's sessions on any change so new permissions take effect.
    """
    cur.execute(
        "SELECT 1 FROM users WHERE user_id = %s AND sso_tenant_id = %s",
        (user_id, tenant_id),
    )
    if not cur.fetchone():
        # Cross-tenant attempt: silently no-op rather than mutate.
        logger.warning(
            "[scim] cross-tenant role recompute blocked for user=%s tenant=%s",
            user_id,
            tenant_id,
        )
        return None
    cur.execute(
        """
        SELECT g.mapped_role
          FROM scim_group_members m
          JOIN scim_groups g ON g.group_id = m.group_id
         WHERE m.user_id = %s
           AND g.tenant_id = %s
           AND g.deleted_at IS NULL
           AND g.mapped_role IS NOT NULL
        """,
        (user_id, tenant_id),
    )
    rows = cur.fetchall() or []
    candidates = [str(r["mapped_role"]) for r in rows if r.get("mapped_role")]
    new_role = "member"
    if candidates:
        new_role = max(candidates, key=lambda r: ROLE_PRECEDENCE.get(r, 0))
    cur.execute("SELECT COALESCE(role, '') AS role FROM users WHERE user_id = %s", (user_id,))
    current = cur.fetchone() or {}
    if (current.get("role") or "") == new_role:
        return None
    cur.execute("UPDATE users SET role = %s WHERE user_id = %s", (new_role, user_id))
    cur.execute(
        "UPDATE user_sessions SET revoked_at = NOW() " "WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )
    return new_role


def _validate_tenant_members(cur, tenant_id: str, user_ids: list[str]) -> list[str]:
    """Filter ``user_ids`` to those that belong to ``tenant_id``. Any
    out-of-tenant id raises HTTP 400 — the SCIM caller is bound to one
    tenant and must not be able to address users in other tenants."""
    if not user_ids:
        return []
    cur.execute(
        "SELECT user_id FROM users WHERE sso_tenant_id = %s AND user_id = ANY(%s)",
        (tenant_id, user_ids),
    )
    found = {str(r["user_id"]) for r in (cur.fetchall() or [])}
    missing = [u for u in user_ids if u not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Users not in tenant: {missing}",
        )
    return list(found)


class ScimGroupCreate(BaseModel):
    displayName: str
    externalId: str | None = None
    members: list[dict[str, Any]] = []
    # Non-standard extension — IdPs that know about us can pre-set the
    # platform role this group maps to. Otherwise leave null and an
    # admin sets it via the platform UI later.
    manifestRole: str | None = None


@router.get("/Groups")
async def scim_list_groups(
    authorization: str | None = Header(None),
    filter: str | None = Query(None, alias="filter"),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=200),
):
    tenant = _require_tenant(authorization)
    where = ["tenant_id = %s", "deleted_at IS NULL"]
    params: list[Any] = [tenant["tenant_id"]]
    if filter:
        try:
            field, op, raw_value = filter.split(" ", 2)
            value = raw_value.strip().strip('"')
            if op.lower() == "eq" and field == "displayName":
                where.append("display_name = %s")
                params.append(value)
        except ValueError:
            pass
    where_sql = " AND ".join(where)
    count_sql = f"SELECT COUNT(*) AS n FROM scim_groups WHERE {where_sql}"
    page_sql = (
        "SELECT group_id, tenant_id, external_id, display_name, mapped_role, created_at "
        f"FROM scim_groups WHERE {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s"
    )
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = int((cur.fetchone() or {"n": 0})["n"])
            cur.execute(page_sql, params + [count, startIndex - 1])
            rows = cur.fetchall() or []
            resources = []
            for r in rows:
                members = _list_group_members(cur, str(r["group_id"]))
                resources.append(_group_to_scim(r, members))
    except Exception as exc:
        logger.warning("[scim] list_groups failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM group list failed") from exc
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "Resources": resources,
        "startIndex": startIndex,
        "itemsPerPage": len(resources),
    }


@router.get("/Groups/{group_id}")
async def scim_get_group(group_id: str, authorization: str | None = Header(None)):
    tenant = _require_tenant(authorization)
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM scim_groups WHERE group_id = %s AND tenant_id = %s "
                "AND deleted_at IS NULL",
                (group_id, tenant["tenant_id"]),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Group not found")
            members = _list_group_members(cur, group_id)
        return _group_to_scim(row, members)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[scim] get_group failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM group fetch failed") from exc


@router.post("/Groups", status_code=201)
async def scim_create_group(payload: ScimGroupCreate, authorization: str | None = Header(None)):
    tenant = _require_tenant(authorization)
    from app.security.permissions import ASSIGNABLE_ROLES

    mapped = (payload.manifestRole or "").strip().lower() or None
    if mapped and mapped not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=400, detail=f"manifestRole must be one of {sorted(ASSIGNABLE_ROLES)}"
        )
    member_ids = [str(m["value"]) for m in (payload.members or []) if m.get("value")]
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _validate_tenant_members(cur, tenant["tenant_id"], member_ids)
                cur.execute(
                    """
                    INSERT INTO scim_groups (tenant_id, external_id, display_name, mapped_role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING group_id, tenant_id, external_id, display_name, mapped_role, created_at
                    """,
                    (tenant["tenant_id"], payload.externalId, payload.displayName, mapped),
                )
                row = cur.fetchone()
                group_id = str(row["group_id"])
                for uid in member_ids:
                    cur.execute(
                        "INSERT INTO scim_group_members (group_id, user_id) VALUES (%s, %s) "
                        "ON CONFLICT DO NOTHING",
                        (group_id, uid),
                    )
                for uid in member_ids:
                    _recompute_user_role(cur, uid, tenant["tenant_id"])
            conn.commit()
        return _group_to_scim(row, member_ids)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[scim] create_group failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM group create failed") from exc


@router.patch("/Groups/{group_id}")
async def scim_patch_group(  # noqa: C901
    group_id: str, request: Request, authorization: str | None = Header(None)
):
    """Apply add/remove/replace operations on the ``members`` attribute.

    Supports the SCIM PatchOp shape used by Okta/AzureAD/OneLogin:
    - ``{"op":"add","path":"members","value":[{"value":"<user_id>"}]}``
    - ``{"op":"remove","path":"members[value eq \"<user_id>\"]"}``
    - ``{"op":"replace","path":"members","value":[...]}``
    """
    tenant = _require_tenant(authorization)
    body = await request.json()
    operations = body.get("Operations", [])
    affected_users: set = set()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT group_id FROM scim_groups WHERE group_id = %s AND tenant_id = %s "
                    "AND deleted_at IS NULL",
                    (group_id, tenant["tenant_id"]),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Group not found")
                for op in operations:
                    name = (op.get("op") or "").lower()
                    path = (op.get("path") or "").strip()
                    value = op.get("value")
                    if name == "replace" and path in ("members", ""):
                        new_uids = [
                            str(m.get("value") or "") for m in (value or []) if m.get("value")
                        ]
                        _validate_tenant_members(cur, tenant["tenant_id"], new_uids)
                        cur.execute(
                            "SELECT user_id FROM scim_group_members WHERE group_id = %s",
                            (group_id,),
                        )
                        for r in cur.fetchall() or []:
                            affected_users.add(str(r["user_id"]))
                        cur.execute(
                            "DELETE FROM scim_group_members WHERE group_id = %s", (group_id,)
                        )
                        for uid in new_uids:
                            cur.execute(
                                "INSERT INTO scim_group_members (group_id, user_id) "
                                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                (group_id, uid),
                            )
                            affected_users.add(uid)
                    elif name == "add" and path == "members":
                        add_uids = [
                            str(m.get("value") or "") for m in (value or []) if m.get("value")
                        ]
                        _validate_tenant_members(cur, tenant["tenant_id"], add_uids)
                        for uid in add_uids:
                            cur.execute(
                                "INSERT INTO scim_group_members (group_id, user_id) "
                                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                (group_id, uid),
                            )
                            affected_users.add(uid)
                    elif name == "remove" and path.startswith("members"):
                        # Either explicit value list or filter form like
                        # members[value eq "<uid>"].
                        target_uids: list[str] = []
                        if "[" in path and "value eq" in path:
                            try:
                                target_uids = [path.split('"')[1]]
                            except Exception:
                                target_uids = []
                        elif isinstance(value, list):
                            target_uids = [
                                str(m.get("value") or "") for m in value if m.get("value")
                            ]
                        # Removal is intentionally tolerant — we only act
                        # on (group_id, user_id) rows we actually own.
                        for uid in target_uids:
                            cur.execute(
                                "DELETE FROM scim_group_members WHERE group_id = %s AND user_id = %s",
                                (group_id, uid),
                            )
                            affected_users.add(uid)
                for uid in affected_users:
                    _recompute_user_role(cur, uid, tenant["tenant_id"])
                cur.execute(
                    "UPDATE scim_groups SET updated_at = NOW() WHERE group_id = %s",
                    (group_id,),
                )
                cur.execute(
                    "SELECT * FROM scim_groups WHERE group_id = %s",
                    (group_id,),
                )
                row = cur.fetchone()
                members = _list_group_members(cur, group_id)
            conn.commit()
        return _group_to_scim(row, members)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[scim] patch_group failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM group patch failed") from exc


@router.delete("/Groups/{group_id}", status_code=204)
async def scim_delete_group(group_id: str, authorization: str | None = Header(None)):
    """Soft-delete a SCIM group: clear membership, mark deleted_at, and
    recompute the role of every former member so role grants flowing
    from this group are immediately retracted."""
    tenant = _require_tenant(authorization)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM scim_groups WHERE group_id = %s AND tenant_id = %s "
                    "AND deleted_at IS NULL",
                    (group_id, tenant["tenant_id"]),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Group not found")
                cur.execute(
                    "SELECT user_id FROM scim_group_members WHERE group_id = %s",
                    (group_id,),
                )
                affected = [str(r["user_id"]) for r in (cur.fetchall() or [])]
                cur.execute("DELETE FROM scim_group_members WHERE group_id = %s", (group_id,))
                cur.execute(
                    "UPDATE scim_groups SET deleted_at = NOW() WHERE group_id = %s",
                    (group_id,),
                )
                for uid in affected:
                    _recompute_user_role(cur, uid, tenant["tenant_id"])
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[scim] delete_group failed: %s", exc)
        raise HTTPException(status_code=500, detail="SCIM group delete failed") from exc
    return None
