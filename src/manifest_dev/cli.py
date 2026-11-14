"""CLI entrypoints for local Manifest development."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

COMMAND_TO_SCRIPT = {
    "setup": "setup_project.py",
    "start": "start_app.py",
    "stop": "stop_app.py",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the developer CLI."""
    parser = argparse.ArgumentParser(
        prog="manifest-dev",
        description="Bootstrap and run the Manifest full-stack workspace.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name, help_text in (
        ("setup", "Install backend and frontend dependencies."),
        ("start", "Run the backend and frontend development servers."),
        ("stop", "Stop any local Manifest services running on the default ports."),
    ):
        subparsers.add_parser(command_name, help=help_text, description=help_text)

    return parser


def run_command(command: str, extra_args: Sequence[str] | None = None) -> int:
    """Run one of the repository helper scripts."""
    script_name = COMMAND_TO_SCRIPT[command]
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path), *(extra_args or ())]
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    """CLI main entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_command(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
