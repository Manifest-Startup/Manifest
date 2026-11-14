"""Dedicated admin-action audit trail (SEC-066).

Lives alongside ``security_audit_service`` but is a separate table so
the SOC 2 / ISO 27001 evidence pull for "privileged operations" doesn't
need to filter through the high-volume security event firehose.

Every admin endpoint should call ``record_admin_event(...)`` after the
action, including the step-up verification ID that authorised it. The
verification ID makes it trivial to prove during audit that no admin
action fires without a recent re-auth.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.db.database import get_db_connection
from app.utils.logger import logger


def _json_safe(value: dict[str, Any] | None) -> str:
    try:
        return json.dumps(value or {}, default=str)
    except Exception:
        return "{}"


def record_admin_event(
    *,
    actor_user_id: str,
    action: str,
    target_user_id: str | None = None,
    resource: str | None = None,
    request_ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
    step_up_verification_id: str | None = None,
) -> None:
    payload = {
        "event_id": str(uuid.uuid4()),
        "actor_user_id": actor_user_id,
        "target_user_id": target_user_id,
        "action": action,
        "resource": resource,
        "request_ip": request_ip,
        "user_agent": user_agent,
        "metadata": metadata or {},
        "step_up_verification_id": step_up_verification_id,
    }
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_audit_events
                        (event_id, actor_user_id, target_user_id, action, resource,
                         request_ip, user_agent, metadata, step_up_verification_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                    """,
                    (
                        payload["event_id"],
                        actor_user_id,
                        target_user_id,
                        action,
                        resource,
                        request_ip,
                        user_agent,
                        _json_safe(metadata),
                        step_up_verification_id,
                    ),
                )
            conn.commit()
    except Exception as exc:
        logger.warning("[admin_audit] persist failed action=%s: %s", action, exc)
        logger.info("[admin_audit] %s", payload)
