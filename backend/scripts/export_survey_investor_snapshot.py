#!/usr/bin/env python3
"""Emit anonymized survey aggregates as JSON (stdout) for decks or private docs.

Excludes raw free-text fields and PII. Use with service-role DB access only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from app.db.database import create_database_client
from app.services.survey_ops_service import survey_ops_service


def main() -> None:
    window = int(os.getenv("SNAPSHOT_WINDOW_DAYS", "90"))
    db = create_database_client()
    summary = survey_ops_service.get_summary(db, window_days=window, include_issue_candidates=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
