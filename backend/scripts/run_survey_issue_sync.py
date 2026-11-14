"""Summarize survey signals and optionally sync recurring themes to GitHub Issues."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.db.database import create_database_client
from app.services.operations.survey_ops import survey_ops_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Manifest survey feedback and optionally create GitHub issues.")
    parser.add_argument("--window-days", type=int, default=90, help="Rolling survey window to analyze.")
    parser.add_argument("--max-issues", type=int, default=6, help="Maximum number of issue candidates to return or create.")
    parser.add_argument("--min-theme-count", type=int, default=2, help="Minimum recurring signal count before an issue candidate is emitted.")
    parser.add_argument(
        "--github-repo",
        default=None,
        help="Optional repo override in owner/name format. Defaults to MANIFEST_GITHUB_REPO.",
    )
    parser.add_argument(
        "--no-create-issues",
        action="store_true",
        help="Generate issue candidates without creating GitHub issues.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the analysis and print candidates without creating GitHub issues.",
    )
    parser.add_argument(
        "--extra-label",
        action="append",
        default=[],
        help="Optional extra label to add to each created GitHub issue. May be passed multiple times.",
    )
    return parser.parse_args()


async def _main() -> int:
    args = parse_args()
    db = create_database_client()
    result = await survey_ops_service.sync_issues(
        db,
        window_days=args.window_days,
        max_issues=args.max_issues,
        min_theme_count=args.min_theme_count,
        create_github_issues=not args.no_create_issues,
        dry_run=args.dry_run,
        github_repo=args.github_repo,
        extra_labels=args.extra_label,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
