"""Where the CLI keeps its session: ``~/.config/manifest/cli.json`` (mode 0600).

``MANIFEST_CONFIG`` overrides the path; ``MANIFEST_API_URL`` and ``MANIFEST_API_TOKEN``
override the stored base URL and token (handy for CI or a second deployment).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://manifeststartup.com"


def config_path() -> Path:
    explicit = os.environ.get("MANIFEST_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "manifest" / "cli.json"


def load() -> dict[str, Any]:
    path = config_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, Any]) -> Path:
    """Write the config atomically with owner-only permissions (dir 0700, file 0600)."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def base_url(override: str | None = None) -> str:
    value = override or os.environ.get("MANIFEST_API_URL") or load().get("base_url")
    return str(value or DEFAULT_BASE_URL).rstrip("/")


def token(override: str | None = None) -> str | None:
    return override or os.environ.get("MANIFEST_API_TOKEN") or load().get("token") or None
