"""Retention Exception Register loader.

Reads the YAML register pointed to by
``RETENTION_EXCEPTIONS_PATH`` (default
``backend/config/retention_exceptions.yaml``) and exposes a typed view
for the privacy retention orchestrator and the trust-center endpoint.

Public-facing API only ever surfaces *non-sensitive* fields (id, scope,
reason, opened_at, expected_close, approved_by, ticket). The raw SQL
``match`` predicate is **never** included in API responses because it
may itself contain personal identifiers — it is internal to the
orchestrator.

This is intentionally a small, dependency-light module: the register is
operationally critical evidence (SOC 2 CC6.5, GDPR Art. 5(1)(e)) and we
want the loader to be auditable at a glance.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.utils.logger import logger

# Conservative allowlist for the SQL ``match`` predicate. The register
# is operator-controlled, but defence-in-depth: even a tampered register
# entry must not be able to inject ``;`` (multi-statement), comments
# (``--``, ``/* */``), or arbitrary keywords like DROP/UPDATE/INSERT
# into a destructive DELETE clause. Anything containing these tokens is
# rejected at load time and the entry is skipped (which the orchestrator
# treats as a malformed register → fail-safe abort).
_FORBIDDEN_MATCH_TOKENS = (
    ";",
    "--",
    "/*",
    "*/",
    "\\",
)
_FORBIDDEN_MATCH_PATTERNS = (
    re.compile(r"\bdrop\b", re.IGNORECASE),
    re.compile(r"\binsert\b", re.IGNORECASE),
    re.compile(r"\bupdate\b", re.IGNORECASE),
    re.compile(r"\bdelete\b", re.IGNORECASE),
    re.compile(r"\bgrant\b", re.IGNORECASE),
    re.compile(r"\brevoke\b", re.IGNORECASE),
    re.compile(r"\btruncate\b", re.IGNORECASE),
    re.compile(r"\battach\b", re.IGNORECASE),
    re.compile(r"\bcopy\b", re.IGNORECASE),
    re.compile(r"\bunion\b", re.IGNORECASE),
    re.compile(r"\binto\b", re.IGNORECASE),
    re.compile(r"pg_", re.IGNORECASE),
)


def _match_is_safe(match: str) -> bool:
    if not match or len(match) > 500:
        return False
    if any(token in match for token in _FORBIDDEN_MATCH_TOKENS):
        return False
    return not any(p.search(match) for p in _FORBIDDEN_MATCH_PATTERNS)


DEFAULT_PATH = os.path.join("backend", "config", "retention_exceptions.yaml")
PUBLIC_FIELDS = (
    "id",
    "scope",
    "reason",
    "approved_by",
    "opened_at",
    "expected_close",
    "ticket",
)


@dataclass(frozen=True)
class RetentionException:
    id: str
    scope: str
    reason: str
    approved_by: str
    opened_at: str
    expected_close: str | None = None
    ticket: str | None = None
    match: str | None = field(default=None, repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in PUBLIC_FIELDS if getattr(self, k, None)}


def _exception_from_entry(entry: dict, match_val: str | None) -> RetentionException:
    """Map one validated register row to a RetentionException (raises KeyError on missing keys)."""
    return RetentionException(
        id=str(entry["id"]),
        scope=str(entry["scope"]),
        reason=str(entry["reason"]),
        approved_by=str(entry.get("approved_by") or "unknown"),
        opened_at=str(entry.get("opened_at") or ""),
        expected_close=(
            str(entry["expected_close"]) if entry.get("expected_close") is not None else None
        ),
        ticket=str(entry["ticket"]) if entry.get("ticket") is not None else None,
        match=match_val,
    )


def _resolve_path(path: str | None) -> str:
    return path or os.environ.get("RETENTION_EXCEPTIONS_PATH") or DEFAULT_PATH


def load_register(path: str | None = None) -> list[RetentionException]:
    """Load and validate the register. Returns ``[]`` on any error
    rather than raising — the retention job must keep running even if
    the register file is missing or malformed (fail-safe: stricter
    deletion is safer than permissive retention)."""
    target = _resolve_path(path)
    if not os.path.exists(target):
        return []
    try:
        import yaml  # local import keeps the orchestrator import-light
    except Exception:
        logger.warning("[retention_exceptions] PyYAML not installed; treating register as empty")
        return []
    try:
        with open(target, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except Exception:
        logger.exception("[retention_exceptions] failed to read %s", target)
        return []

    raw = doc.get("exceptions") if isinstance(doc, dict) else None
    if not isinstance(raw, list):
        return []

    out: list[RetentionException] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            match_val = entry.get("match")
            if match_val is not None:
                match_val = str(match_val)
                if not _match_is_safe(match_val):
                    logger.warning(
                        "[retention_exceptions] rejecting entry %s: match predicate failed allowlist",
                        entry.get("id"),
                    )
                    continue
            out.append(_exception_from_entry(entry, match_val))
        except KeyError as exc:
            logger.warning("[retention_exceptions] skipping malformed entry (missing %s)", exc)
            continue
    return out


class RegisterLoadError(Exception):
    """Raised by :func:`load_register_strict` for any register problem."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def load_register_strict(path: str | None = None) -> list[RetentionException]:  # noqa: C901
    """Single-read, fail-loud loader used by the retention orchestrator.

    Performs **one** file read, validates shape, and returns the list of
    well-formed entries — or raises :class:`RegisterLoadError` with a
    diagnostic code on *any* problem (file unreadable, YAML parse
    error, root not a mapping, missing/invalid ``exceptions`` key,
    rejected match predicate, partial entry drop). Eliminates the
    TOCTOU window between a separate validate-then-load pair so the
    orchestrator cannot fail-open on a transient fault between the
    two reads."""
    target = _resolve_path(path)
    if not os.path.exists(target):
        return []
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RegisterLoadError("register_yaml_unavailable") from exc
    try:
        with open(target, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except Exception as exc:
        raise RegisterLoadError(f"register_yaml_error:{type(exc).__name__}") from exc
    # An *existing but empty/truncated* register is treated as a hard
    # error: legal-hold safety requires that the only valid empty state
    # is a *missing* file. A truncated/cleared register would otherwise
    # silently drop every hold.
    if doc is None:
        raise RegisterLoadError("register_empty_file")
    if not isinstance(doc, dict):
        raise RegisterLoadError("register_root_not_mapping")
    if "exceptions" not in doc:
        raise RegisterLoadError("register_missing_exceptions_key")
    raw_list = doc["exceptions"]
    if not isinstance(raw_list, list):
        raise RegisterLoadError("register_exceptions_not_list")
    if len(raw_list) == 0:
        return []

    out: list[RetentionException] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            raise RegisterLoadError("register_entries_invalid")
        try:
            match_val = entry.get("match")
            if match_val is not None:
                match_val = str(match_val)
                if not _match_is_safe(match_val):
                    raise RegisterLoadError("register_match_predicate_rejected")
            out.append(_exception_from_entry(entry, match_val))
        except RegisterLoadError:
            raise
        except KeyError:
            raise RegisterLoadError("register_entries_invalid") from None
    return out


def validate_register_shape(path: str | None = None) -> str | None:
    """Return ``None`` when the register file is shape-correct
    (``{exceptions: <list>}``), else a short error code describing the
    problem. The orchestrator uses this to decide whether to fail-safe
    abort destructive deletions. A *missing* file is treated as the
    valid empty state and returns ``None``."""
    target = _resolve_path(path)
    if not os.path.exists(target):
        return None
    try:
        import yaml
    except Exception:
        return "register_yaml_unavailable"
    try:
        with open(target, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except Exception as exc:
        return f"register_yaml_error:{type(exc).__name__}"
    # Empty file is allowed.
    if doc is None:
        return None
    if not isinstance(doc, dict):
        return "register_root_not_mapping"
    if "exceptions" not in doc:
        return "register_missing_exceptions_key"
    if not isinstance(doc["exceptions"], list):
        return "register_exceptions_not_list"
    raw_list = doc["exceptions"]
    if len(raw_list) == 0:
        return None
    # If at least one entry was supplied but loading produced none,
    # treat the entire register as malformed (fail-safe).
    loaded = load_register(path)
    if not loaded:
        return "register_entries_invalid"
    if len(loaded) < len(raw_list):
        return "register_entries_partially_invalid"
    return None


def public_view(path: str | None = None) -> list[dict[str, Any]]:
    """Auditor / trust-center safe view: redacts the SQL match clause."""
    return [e.to_public_dict() for e in load_register(path)]


__all__ = [
    "RegisterLoadError",
    "RetentionException",
    "load_register",
    "load_register_strict",
    "public_view",
    "validate_register_shape",
]
