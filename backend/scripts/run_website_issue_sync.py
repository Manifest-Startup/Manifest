"""Run the Manifest website audit and optional GitHub issue sync from the CLI."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.services.operations.website_issue_sync import website_issue_sync_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a public website and sync findings to GitHub Issues.")
    parser.add_argument("--target-url", default="https://manifeststartup.com", help="Public URL to audit.")
    parser.add_argument("--max-pages", type=int, default=6, help="Maximum number of pages to crawl.")
    parser.add_argument("--max-issues", type=int, default=6, help="Maximum number of issues to return or create.")
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
        help="Run the audit and print candidates without creating GitHub issues.",
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
    result = await website_issue_sync_service.audit_website_and_sync_issues(
        args.target_url,
        max_pages=args.max_pages,
        max_issues=args.max_issues,
        create_github_issues=not args.no_create_issues,
        dry_run=args.dry_run,
        github_repo=args.github_repo,
        extra_labels=args.extra_label,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
