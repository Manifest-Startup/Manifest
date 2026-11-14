#!/usr/bin/env python3
"""
Maintenance: delete oldest auto snapshots per idea when count exceeds
AUTO_VERSION_MAX_AUTO_PER_IDEA (see backend/app/services/ideas/versioning_policy.py).

Run from repo root with backend on PYTHONPATH, e.g.:

  PYTHONPATH=backend python scripts/prune_auto_idea_versions.py
"""

from __future__ import annotations

import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))


async def _main() -> None:
    from app.db.database import db_client
    from app.services.ideas.collaboration import create_collaboration_service

    svc = create_collaboration_service(db_client)
    n = await svc.prune_excess_auto_versions_all_ideas()
    print(f"Removed {n} auto version row(s) total.")


if __name__ == "__main__":
    asyncio.run(_main())
