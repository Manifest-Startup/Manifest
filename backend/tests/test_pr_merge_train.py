"""Tests for the Manifest PR Merge Train.

Exercises the *decision* layer of ``backend/scripts/run_pr_merge_train.py``
(branch-protection guard, PR eligibility + safest-first ordering, conflict
classification, lockfile-dir derivation, env parsing) — all without git, the
network, or a real merge.
"""

from __future__ import annotations

import os
import sys

# The orchestrator lives under backend/scripts (not importable as app.*).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import run_pr_merge_train as mt  # noqa: E402


def _pr(
    number, *, base="main", draft=False, dependabot=False, update_type="", title="t", head=None
):
    return mt.PullRequest(
        number=number,
        title=title,
        head_ref=head or f"branch-{number}",
        base_ref=base,
        is_draft=draft,
        is_dependabot=dependabot,
        update_type=update_type,
    )


# ---------- protected-branch guard ----------


def test_main_is_always_protected_even_if_omitted():
    protected = mt.normalize_protected("autopilot")
    assert "main" in protected and "autopilot" in protected


def test_normalize_protected_defaults_when_empty():
    assert mt.normalize_protected(None) == {"main", "autopilot"}
    assert mt.normalize_protected("") == {"main", "autopilot"}


def test_normalize_protected_extra_branches():
    assert mt.normalize_protected("main,autopilot,release") == {"main", "autopilot", "release"}


def test_should_delete_branch_blocks_protected():
    protected = mt.normalize_protected("main,autopilot")
    assert mt.should_delete_branch("dependabot/pip/foo", protected=protected) is True
    assert mt.should_delete_branch("autopilot", protected=protected) is False
    assert mt.should_delete_branch("main", protected=protected) is False
    assert mt.should_delete_branch("", protected=protected) is False
    assert mt.should_delete_branch("  ", protected=protected) is False


# ---------- eligibility ----------


def test_eligible_excludes_other_base_and_drafts_by_default():
    prs = [
        _pr(1),
        _pr(2, base="develop"),
        _pr(3, draft=True),
    ]
    got = mt.eligible_prs(prs, base="main", include_drafts=False)
    assert [p.number for p in got] == [1]


def test_eligible_includes_drafts_when_requested():
    prs = [_pr(1), _pr(3, draft=True)]
    got = mt.eligible_prs(prs, base="main", include_drafts=True)
    assert {p.number for p in got} == {1, 3}


# ---------- ordering (safest first) ----------


def test_merge_order_dependabot_patch_minor_first_then_number():
    prs = [
        _pr(10, dependabot=False),  # human → last
        _pr(11, dependabot=True, update_type="major"),  # dep but risky
        _pr(12, dependabot=True, update_type="patch"),  # safest
        _pr(9, dependabot=True, update_type="minor"),  # safest, lower number
    ]
    order = [p.number for p in mt.merge_order(prs)]
    # patch/minor deps first (oldest first), then other deps, then humans.
    assert order == [9, 12, 11, 10]


def test_merge_order_stable_by_number_within_same_risk():
    prs = [_pr(5), _pr(2), _pr(8)]
    assert [p.number for p in mt.merge_order(prs)] == [2, 5, 8]


# ---------- conflict classification ----------


def test_classify_clean_when_no_conflicts():
    assert mt.classify_conflict([]) == "clean"


def test_classify_lockfile_only():
    assert mt.classify_conflict(["frontend/package-lock.json"]) == "lockfile_only"


def test_classify_code_when_any_real_conflict():
    assert mt.classify_conflict(["backend/requirements.txt"]) == "code"
    # a lockfile mixed with real code is still code (human needed).
    assert mt.classify_conflict(["frontend/package-lock.json", "frontend/src/App.tsx"]) == "code"


def test_classify_package_json_is_code_not_lockfile():
    # package.json conflicts are real content we will not guess at.
    assert mt.classify_conflict(["frontend/package.json"]) == "code"


# ---------- lockfile dirs ----------


def test_lockfile_dirs_dedup_and_parent():
    dirs = mt.lockfile_dirs(
        ["frontend/package-lock.json", "extensions/manifest-dev/package-lock.json"]
    )
    assert dirs == ["frontend", "extensions/manifest-dev"]


# ---------- dependabot title parsing ----------


def test_semver_bump_from_title():
    assert mt._semver_bump_from_title("Bump vite from 7.3.5 to 8.0.16") == "major"
    assert mt._semver_bump_from_title("Bump react-router from 7.15.0 to 7.16.0") == "minor"
    assert mt._semver_bump_from_title("Bump qs from 6.14.1 to 6.14.2") == "patch"
    assert mt._semver_bump_from_title("Update typing-extensions requirement") == ""


# ---------- env parsing ----------


def test_merge_train_enabled_only_for_truthy(monkeypatch):
    for val, expected in [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("on", True),
        ("false", False),
        ("", False),
        ("no", False),
    ]:
        monkeypatch.setenv("PR_MERGE_TRAIN_ENABLED", val)
        assert mt.merge_train_enabled() is expected


def test_env_bool_default(monkeypatch):
    monkeypatch.delenv("PR_MERGE_TRAIN_RUN_CHECKS", raising=False)
    assert mt._env_bool("PR_MERGE_TRAIN_RUN_CHECKS", default=True) is True
    monkeypatch.setenv("PR_MERGE_TRAIN_RUN_CHECKS", "false")
    assert mt._env_bool("PR_MERGE_TRAIN_RUN_CHECKS", default=True) is False
