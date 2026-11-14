"""Tests for the Manifest Security Autofix loop.

Exercises the *decision* layer of ``backend/scripts/run_security_autofix.py``
(npm-dir discovery, audit-summary parsing, semver compare, Dependabot-alert →
pip-bump mapping, requirements.txt rewriting, env parsing) — without git, npm,
or the network.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import run_security_autofix as sa  # noqa: E402

# ---------- npm dir discovery ----------


def test_discover_npm_dirs_skips_node_modules_and_dedupes():
    paths = [
        "frontend/package-lock.json",
        "frontend/node_modules/foo/package-lock.json",
        "extensions/manifest-dev/package-lock.json",
        "frontend/package.json",  # not a lockfile
        "frontend/package-lock.json",  # dup
    ]
    assert sa.discover_npm_dirs(paths) == [
        "frontend",
        "extensions/manifest-dev",
    ]


# ---------- audit summary ----------


def test_parse_audit_summary_counts():
    blob = (
        '{"metadata":{"vulnerabilities":'
        '{"critical":1,"high":2,"moderate":3,"low":4,"info":0,"total":10}}}'
    )
    s = sa.parse_audit_summary(blob)
    assert s == {"total": 10, "critical": 1, "high": 2, "moderate": 3, "low": 4}


def test_parse_audit_summary_handles_garbage():
    assert sa.parse_audit_summary("not json")["total"] == 0
    assert sa.parse_audit_summary("")["total"] == 0


# ---------- semver compare ----------


def test_semver_ge():
    assert sa._semver_ge("1.16.0", "1.16.0") is True
    assert sa._semver_ge("1.16.1", "1.16.0") is True
    assert sa._semver_ge("2.0.0", "1.99.99") is True
    assert sa._semver_ge("1.15.2", "1.16.0") is False
    assert sa._semver_ge("0.315.7", "0.315.6") is True


# ---------- dependabot alert → pip bumps ----------


def _alert(eco, name, manifest, patched, state="open"):
    return {
        "state": state,
        "dependency": {
            "package": {"ecosystem": eco, "name": name},
            "manifest_path": manifest,
        },
        "security_vulnerability": {"first_patched_version": {"identifier": patched}},
    }


def test_desired_pip_bumps_filters_ecosystem_and_state():
    alerts = [
        _alert("pip", "PyJWT", "backend/requirements.txt", "2.13.0"),
        _alert("npm", "axios", "frontend/package-lock.json", "1.16.0"),  # not pip
        _alert("pip", "strawberry", "backend/requirements.txt", "0.315.7", state="fixed"),
    ]
    bumps = sa.desired_pip_bumps(alerts)
    assert bumps == [sa.PipBump("backend/requirements.txt", "pyjwt", "2.13.0")]


def test_desired_pip_bumps_keeps_highest_patched():
    alerts = [
        _alert("pip", "pyjwt", "backend/requirements.txt", "2.9.0"),
        _alert("pip", "pyjwt", "backend/requirements.txt", "2.13.0"),
        _alert("pip", "pyjwt", "backend/requirements.txt", "2.12.1"),
    ]
    bumps = sa.desired_pip_bumps(alerts)
    assert bumps == [sa.PipBump("backend/requirements.txt", "pyjwt", "2.13.0")]


def test_desired_pip_bumps_skips_alerts_without_patch():
    alerts = [
        {
            "state": "open",
            "dependency": {
                "package": {"ecosystem": "pip", "name": "foo"},
                "manifest_path": "backend/requirements.txt",
            },
            "security_vulnerability": {"first_patched_version": None},
        }
    ]
    assert sa.desired_pip_bumps(alerts) == []


# ---------- requirements rewriting ----------


def test_bump_requirements_line_upgrades_when_below():
    assert sa.bump_requirements_line("PyJWT==2.10.1", "pyjwt", "2.13.0") == "PyJWT==2.13.0"


def test_bump_requirements_line_noop_when_already_at_or_above():
    assert sa.bump_requirements_line("PyJWT==2.13.0", "pyjwt", "2.13.0") is None
    assert sa.bump_requirements_line("PyJWT==2.14.0", "pyjwt", "2.13.0") is None


def test_bump_requirements_line_ignores_other_packages():
    assert sa.bump_requirements_line("requests==2.0.0", "pyjwt", "2.13.0") is None


def test_bump_requirements_line_preserves_indent_and_name_case():
    assert sa.bump_requirements_line("  PyJWT>=2.10.1", "pyjwt", "2.13.0") == "  PyJWT==2.13.0"


def test_apply_pip_bumps_only_touches_relevant_lines():
    content = "fastapi==0.1.0\nPyJWT==2.10.1\n# comment PyJWT==9\nstrawberry-graphql==0.274.3\n"
    bumps = [
        sa.PipBump("backend/requirements.txt", "PyJWT", "2.13.0"),
        sa.PipBump("backend/requirements.txt", "strawberry-graphql", "0.315.7"),
    ]
    new, changed = sa.apply_pip_bumps(content, bumps)
    assert "PyJWT==2.13.0" in new
    assert "strawberry-graphql==0.315.7" in new
    assert "fastapi==0.1.0" in new  # untouched
    assert "# comment PyJWT==9" in new  # comment untouched
    assert len(changed) == 2
    assert new.endswith("\n")  # trailing newline preserved


def test_apply_pip_bumps_noop_returns_empty_changes():
    content = "fastapi==0.1.0\n"
    new, changed = sa.apply_pip_bumps(content, [sa.PipBump("x", "pyjwt", "2.13.0")])
    assert changed == []
    assert new == content


# ---------- env + summary ----------


def test_is_enabled(monkeypatch):
    for val, expected in [("true", True), ("on", True), ("1", True), ("false", False), ("", False)]:
        monkeypatch.setenv("SECURITY_AUTOFIX_ENABLED", val)
        assert sa.is_enabled() is expected


def test_summarize_delta():
    before = {"total": 12, "high": 9, "moderate": 3}
    after = {"total": 2, "high": 1, "moderate": 1}
    out = sa.summarize_delta(before, after)
    assert "12→2" in out and "high 9→1" in out
