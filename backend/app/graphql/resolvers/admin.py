"""GraphQL resolvers for admin cost, agent-run and production-test analytics and role changes."""

import strawberry
from app.auth.current_user import (
    get_current_session_id_optional,
    get_current_user_id,
)
from app.graphql.resolvers.shared import _request_ip, _user_agent
from app.graphql.types.admin import (
    AdminAgentRunRow,
    AdminCostOverview,
    AdminProductionTestStats,
    _map_admin_agent_run,
    _map_admin_overview,
    _map_admin_test_stats,
)
from app.services.identity.sessions import revoke_all_sessions


@strawberry.type
class AdminQuery:
    @strawberry.field
    async def admin_cost_overview(
        self, info: strawberry.Info, window_days: int | None = None
    ) -> AdminCostOverview:
        """Platform-wide AI cost overview for the last windowDays days."""
        from app.services.ai import admin_costs as admin_cost_service

        payload = admin_cost_service.build_admin_cost_overview(
            db=info.context["db"], window_days=window_days
        )
        return _map_admin_overview(payload)

    @strawberry.field
    async def admin_agent_runs(
        self,
        info: strawberry.Info,
        limit: int = 50,
        agent_kind: str | None = None,
        status: str | None = None,
    ) -> list[AdminAgentRunRow]:
        """Recent agent runs across all users, filterable by kind and status."""
        from app.services.ai import admin_costs as admin_cost_service

        rows = admin_cost_service.list_recent_runs_cross_user(
            db=info.context["db"], limit=limit, agent_kind=agent_kind, status=status
        )
        return [_map_admin_agent_run(r) for r in rows]

    @strawberry.field
    async def admin_production_test_stats(
        self, info: strawberry.Info, hours: int = 24
    ) -> AdminProductionTestStats:
        """Production smoke-test pass rates over the last hours."""
        from app.services.ai import admin_costs as admin_cost_service

        payload = admin_cost_service.build_production_test_health(
            db=info.context["db"], hours=hours
        )
        return _map_admin_test_stats(payload)


@strawberry.type
class AdminMutation:
    @strawberry.mutation
    async def admin_set_user_role(
        self, info: strawberry.Info, target_user_id: str, role: str
    ) -> bool:
        """Admin: change a user's RBAC role.

        Required permission: ``admin.users.write`` (enforced by the
        default-deny extension via FIELD_PERMISSIONS).

        Side effects (SEC-031):
        * Persists the new role on ``users.role``.
        * Forcibly revokes every active session for the target user so
          the new permission grant takes effect immediately and any
          ongoing tokens stop trusting the old role.
        * Emits ``role_changed`` to the security audit log.
        """
        from app.db.database import get_db_connection
        from app.security.permissions import ASSIGNABLE_ROLES, resolve_principal
        from app.security.step_up import (
            DEFAULT_TTL_SECONDS,
            _recent_login_satisfies,
            has_recent_step_up,
        )
        from app.services.compliance.security_audit import record_security_event

        request = info.context["request"]
        actor_id = get_current_user_id(request)
        actor = resolve_principal(actor_id)
        if not actor.has("admin.users.write"):
            raise Exception("admin.users.write permission required.")
        # SEC-026: privileged admin mutations require a fresh identity
        # proof. A recent login (auth_iat) OR a live step-up record both
        # satisfy this — see require_recent_auth in app.security.step_up.
        actor_session_id = get_current_session_id_optional(request)
        if not (
            _recent_login_satisfies(request, DEFAULT_TTL_SECONDS)
            or has_recent_step_up(actor_id, actor_session_id, max_age_seconds=DEFAULT_TTL_SECONDS)
        ):
            raise Exception(
                "Re-authentication required: complete a step-up at "
                "/api/auth/step-up before changing roles."
            )
        new_role = (role or "").strip().lower()
        if new_role not in ASSIGNABLE_ROLES:
            raise Exception(
                f"Role '{role}' is not assignable. Choose one of: "
                + ", ".join(sorted(ASSIGNABLE_ROLES))
            )
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET role = %s WHERE user_id = %s",
                (new_role, target_user_id),
            )
            changed = cur.rowcount > 0
            conn.commit()
        if not changed:
            raise Exception("Target user not found.")
        revoked = revoke_all_sessions(target_user_id)
        record_security_event(
            "role_changed",
            user_id=target_user_id,
            request_ip=_request_ip(info),
            actor_id=actor_id,
            actor_type="user",
            action="role_change",
            target_type="user",
            target_id=target_user_id,
            outcome="success",
            user_agent=_user_agent(info),
            metadata={
                "actor_user_id": actor_id,
                "new_role": new_role,
                "sessions_revoked": revoked,
            },
        )
        # Detector: privilege-escalation watch (pages on grants to admin).
        from app.security.audit_detections import detect_privilege_escalation

        detect_privilege_escalation(
            actor_user_id=actor_id,
            target_user_id=target_user_id,
            new_role=new_role,
        )
        return True
