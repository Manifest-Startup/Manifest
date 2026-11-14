"""Nightly audit-log retention enforcement.

Run with::

    python -m backend.scripts.run_audit_retention

Schedule via cron / systemd-timer to fire once per day. The worker is
idempotent: it only deletes rows older than the configured retention
window (``AUDIT_RETENTION_DAYS``, floor = 365 days) and emits an
``audit_retention_purge`` marker so downstream SIEM tooling can
reconcile the boundary.
"""

from __future__ import annotations

import json
import os
import sys

# Bootstrap import path so the script runs from any CWD (matches the
# pattern used by other backend/scripts/* entry points).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security.audit_retention import enforce_retention  # noqa: E402


def main() -> int:
    result = enforce_retention()
    print(json.dumps({
        "deleted": result.deleted,
        "marker_seq": result.marker_seq,
        "cutoff": result.cutoff.isoformat() if result.cutoff else None,
        "skipped": result.skipped,
        "reason": result.reason,
    }))
    return 1 if result.skipped else 0


if __name__ == "__main__":
    sys.exit(main())
