"""Where this computer keeps the Manifest vault, and moving it.

The vault sync script (``agent-plugin/skills/manifest-vault/scripts/manifest_vault.py``) owns
the folder: it saves the choice in ``~/.config/manifest/vault.json``, moves the files, restarts
background sync and sets the folder icon. This module finds that script and runs it, so the
CLI (``manifest vault-folder``), the bridge (Settings → Storage in the app) and voice all
change the same setting the same way.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_NAME = "manifest_vault.py"


class VaultFolderError(Exception):
    """The vault folder couldn't be read or changed; the message is for the person."""


def _candidates() -> list[Path]:
    home = Path.home()
    found: list[Path] = []
    explicit = os.environ.get("MANIFEST_VAULT_SCRIPT")
    if explicit:
        found.append(Path(explicit).expanduser())
    # The copy background sync runs (installed by `manifest_vault.py install`).
    if platform.system() == "Darwin":
        found.append(home / "Library/Application Support/Manifest" / SCRIPT_NAME)
    else:
        data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
        found.append(data / "manifest-vault" / SCRIPT_NAME)
    # This checkout (the CLI installed from the repo).
    repo = Path(__file__).resolve().parents[3]
    found.append(repo / "agent-plugin/skills/manifest-vault/scripts" / SCRIPT_NAME)
    # The Claude Code plugin, newest version first.
    cache = home / ".claude/plugins/cache/manifest/manifest"
    if cache.is_dir():
        found += sorted(
            cache.glob(f"*/skills/manifest-vault/scripts/{SCRIPT_NAME}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    return found


def script_path() -> Path:
    """The newest vault script on this computer: the one with ``move`` wins."""
    for path in _candidates():
        if path.is_file() and "def cmd_move" in path.read_text(encoding="utf-8", errors="ignore"):
            return path
    raise VaultFolderError(
        "The Manifest vault isn't set up on this computer. Install the Manifest plugin, "
        "then run its vault sign-in (`manifest_vault.py login`)."
    )


def _run(*args: str, timeout: float = 120) -> dict[str, Any]:
    script = script_path()
    try:
        done = subprocess.run(
            [sys.executable, str(script), *args, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise VaultFolderError("Moving the vault took too long; check its folder.") from exc
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip().splitlines()
        raise VaultFolderError(message[-1] if message else "The vault script failed.")
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise VaultFolderError("The vault script gave an answer I couldn't read.") from exc
    if not isinstance(result, dict):
        raise VaultFolderError("The vault script gave an answer I couldn't read.")
    return result


def where() -> dict[str, Any]:
    """{"folder", "source", "exists", "icloud", "icloud_available", "background_sync", "places",
    "on_delete"}"""
    return _run("where")


ON_DELETE = ("delete", "keep")


def set_on_delete(mode: str) -> dict[str, Any]:
    """When a note is deleted in Manifest: "delete" it from this vault too, or "keep" a copy."""
    mode = (mode or "").strip().lower()
    if mode not in ON_DELETE:
        raise VaultFolderError("Choose delete (remove it here too) or keep (keep your copy).")
    _run("on-delete", mode)
    return where()


def move(dest: str) -> dict[str, Any]:
    """Move the vault to ``dest`` (icloud, documents, home or a full path) and remember it."""
    dest = (dest or "").strip()
    if not dest:
        raise VaultFolderError("Say where to move the vault: icloud, documents, home or a path.")
    return _run("move", dest)


def sync_now(timeout: float = 55) -> dict[str, Any]:
    """Run one two-way sync of this computer's vault now (pull-to-refresh in the app)."""
    script = script_path()
    try:
        done = subprocess.run(
            [sys.executable, str(script), "sync"], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise VaultFolderError(
            "Syncing the vault took too long; it keeps syncing in the background."
        ) from exc
    lines = (done.stdout or "").strip().splitlines()
    if done.returncode == 3:  # offline: changes wait and sync later
        return {"ok": False, "offline": True, "report": lines}
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip().splitlines()
        raise VaultFolderError(message[-1] if message else "The vault sync failed.")
    return {"ok": True, "report": lines}
