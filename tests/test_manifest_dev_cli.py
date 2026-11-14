"""Tests for the local developer CLI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from manifest_dev.cli import COMMAND_TO_SCRIPT, PROJECT_ROOT, build_parser, main, run_command


def test_build_parser_requires_a_command() -> None:
    """The CLI should expose the supported subcommands."""
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert set(choices.keys()) == set(COMMAND_TO_SCRIPT.keys())


@patch("manifest_dev.cli.subprocess.run")
def test_run_command_executes_repo_script(mock_run: MagicMock) -> None:
    """Each CLI subcommand should invoke the matching helper script."""
    mock_run.return_value.returncode = 0

    exit_code = run_command("setup")

    assert exit_code == 0
    mock_run.assert_called_once()
    command = mock_run.call_args.args[0]
    assert command[0].endswith("python") or command[0].endswith("python3")
    assert command[1].endswith("scripts/setup_project.py")
    assert mock_run.call_args.kwargs["cwd"] == PROJECT_ROOT
    assert mock_run.call_args.kwargs["check"] is False


@patch("manifest_dev.cli.run_command", return_value=0)
def test_main_dispatches_to_requested_command(mock_run_command: MagicMock) -> None:
    """The CLI entrypoint should delegate to the selected subcommand."""
    exit_code = main(["start"])

    assert exit_code == 0
    mock_run_command.assert_called_once_with("start")
