"""SIEM JSONL stream sink for security-audit events (SEC-068).

Writes one JSON object per line to a rotating file under
``AUDIT_SINK_PATH`` (default ``logs/audit/audit.jsonl``). The intent is
that operations sync this file to a write-once external store
(S3 + Object Lock, GCS bucket-lock, an Elastic / Splunk forwarder, …)
so a compromised app host cannot retroactively rewrite the audit
record. The file format is compatible with most SIEM ingest pipelines
out of the box.

Design choices:

- **Append-only, line-delimited JSON.** Easy to parse, easy to tail,
  cheap to rotate. We never rewrite earlier lines.
- **Daily rotation by date stamp.** A new file is opened the first
  time a write happens on a new UTC date. Older files are left in
  place for the operator's sync agent to pick up.
- **Best-effort.** Sink failures must never break the application
  request path — if the disk is full or the directory is unwritable
  we log a warning and swallow the error. The DB row is the primary
  record; the JSONL stream is a hot copy for off-host preservation.
- **Sensitivity-aware.** Rows tagged ``Sensitivity.SECRET`` are
  serialised without the metadata payload so a secret can never reach
  the export file even if the redactor missed something.
- **Opt-in.** Disabled unless ``AUDIT_SINK_ENABLED`` is truthy, so
  unit tests and the unconfigured dev shell don't spew files.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.security.audit_chain import Category, Sensitivity, Severity
from app.utils.logger import logger

# Categories whose metadata is deliberately suppressed from the off-host
# SIEM stream by default. The DB row keeps the full payload (sanitised),
# but the export carries only the chain coordinates so a forwarder
# misconfiguration can't fan out high-risk metadata to extra
# destinations. Operators can opt back in with AUDIT_SINK_INCLUDE_METADATA=1
# for the categories below if their SIEM is in a tightly-controlled
# trust zone.
_HIGH_RISK_CATEGORIES = {
    Category.ADMIN.value,
    Category.PRIVACY.value,
    Category.DETECTION.value,
}


def _suppress_metadata(category: str, severity: str, sensitivity: str) -> bool:
    if sensitivity == Sensitivity.SECRET.value:
        return True
    if (os.getenv("AUDIT_SINK_INCLUDE_METADATA") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    if category in _HIGH_RISK_CATEGORIES:
        return True
    return severity in {Severity.CRITICAL.value}


_LOCK = threading.Lock()
_CURRENT_PATH: Path | None = None
_CURRENT_DATE: str | None = None


def _enabled() -> bool:
    raw = (os.getenv("AUDIT_SINK_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _base_dir() -> Path:
    raw = (os.getenv("AUDIT_SINK_PATH") or "").strip()
    if raw:
        path = Path(raw)
        # If the operator gave us a file path, use its parent for rotation.
        return path if path.suffix == "" else path.parent
    return Path("logs/audit")


def _file_for_today(now: datetime) -> Path:
    base = _base_dir()
    base.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d")
    return base / f"audit-{stamp}.jsonl"


def _rotated_path(now: datetime) -> Path:
    """Return the active path, rotating on UTC date change."""
    global _CURRENT_PATH, _CURRENT_DATE
    stamp = now.strftime("%Y-%m-%d")
    if stamp != _CURRENT_DATE or _CURRENT_PATH is None:
        _CURRENT_DATE = stamp
        _CURRENT_PATH = _file_for_today(now)
    return _CURRENT_PATH


def _serialise(
    *,
    event_id: str,
    event_type: str,
    category: str,
    severity: str,
    sensitivity: str,
    user_id: str | None,
    request_ip: str | None,
    session_id: str | None,
    request_id: str | None,
    metadata: Mapping[str, Any],
    event_hash: str,
    prev_hash: str,
    created_at_iso: str,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    tenant_id: str | None = None,
    user_agent: str | None = None,
    outcome: str | None = None,
) -> str:
    record: dict[str, Any] = {
        "ts": created_at_iso,
        "event_id": event_id,
        "event_type": event_type,
        "category": category,
        "severity": severity,
        "sensitivity": sensitivity,
        "user_id": user_id,
        "request_ip": request_ip,
        "session_id": session_id,
        "request_id": request_id,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "tenant_id": tenant_id,
        "user_agent": user_agent,
        "outcome": outcome,
        "event_hash": event_hash,
        "prev_hash": prev_hash,
    }
    if _suppress_metadata(category, severity, sensitivity):
        # Drop the payload entirely — only the chain coordinates are exported.
        # Defence in depth on top of sanitize_metadata: even if the redactor
        # missed a secret, the export still doesn't carry it.
        record["metadata_omitted"] = True
    else:
        record["metadata"] = dict(metadata or {})
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)


def emit(
    *,
    event_id: str,
    event_type: str,
    category: str,
    severity: str,
    sensitivity: str,
    user_id: str | None,
    request_ip: str | None,
    session_id: str | None,
    request_id: str | None,
    metadata: Mapping[str, Any],
    event_hash: str,
    prev_hash: str,
    created_at_iso: str | None = None,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    tenant_id: str | None = None,
    user_agent: str | None = None,
    outcome: str | None = None,
) -> None:
    """Append one record to the active JSONL file.

    Silently noop when ``AUDIT_SINK_ENABLED`` is unset. All errors are
    logged at WARNING and swallowed so the request path is never
    affected by a sink outage.
    """
    if not _enabled():
        return
    now = datetime.now(timezone.utc)
    line = _serialise(
        event_id=event_id,
        event_type=event_type,
        category=category,
        severity=severity,
        sensitivity=sensitivity,
        user_id=user_id,
        request_ip=request_ip,
        session_id=session_id,
        request_id=request_id,
        metadata=metadata,
        event_hash=event_hash,
        prev_hash=prev_hash,
        created_at_iso=created_at_iso or now.isoformat(),
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=target_id,
        tenant_id=tenant_id,
        user_agent=user_agent,
        outcome=outcome,
    )
    try:
        with _LOCK:
            target = _rotated_path(now)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")
    except Exception as exc:  # pragma: no cover - sink is best-effort
        logger.warning("[audit_sink] write failed: %s", exc)


def current_path() -> Path | None:
    """Test / introspection helper — returns the file we'd write to next."""
    if not _enabled():
        return None
    return _rotated_path(datetime.now(timezone.utc))


def reset_for_test() -> None:  # pragma: no cover - test helper
    global _CURRENT_PATH, _CURRENT_DATE
    _CURRENT_PATH = None
    _CURRENT_DATE = None
