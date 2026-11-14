#!/usr/bin/env python3
"""Plan + generate release notes for `.github/workflows/auto-release.yml`.

Two modes:
- `plan`  → reads commits since the previous `vX.Y.Z` tag, decides the
            SemVer bump, and writes `prev_tag`, `next_tag`, `bump` to
            `$GITHUB_OUTPUT` (or stdout when run locally).
- `notes` → prints the release body to stdout, grouped by Conventional
            Commit category, with a footer link to the diff and to the
            heavy release pipeline.

Both modes share a single parse pass so the planning and the cut never
disagree.

Bump policy:
    feat!: / `BREAKING CHANGE`       → major
    feat:                            → minor
    fix: / perf: / security: /
      revert: / refactor:            → patch
    chore: / docs: / test: / ci: /
      build: / style:                → not user-visible; no release
    anything not matching prefix     → treated as patch ("Other")
                                       only if at least one user-visible
                                       commit also exists in the range.

`security:` is not a real Conventional Commit type but is used heavily in
this repo (e.g. `fix(security): …`). Both forms are recognised.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass

REPO_URL = "https://github.com/Manifest-Startup/Manifest"


@dataclass(frozen=True)
class Commit:
    sha: str
    short: str
    subject: str
    ctype: str          # parsed type: feat, fix, perf, security, …
    scope: str | None   # parsed scope or None
    breaking: bool
    pr: str | None      # `#123` if subject ends with `(#123)`


_PR_RE = re.compile(r"\s*\(#(\d+)\)\s*$")
# Subject parsing: `type(scope)!: description` or `type!: description` or
# `type(scope): description` or `type: description`.
_SUBJECT_RE = re.compile(
    r"^(?P<type>[a-zA-Z][a-zA-Z0-9_-]*)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<bang>!)?"
    r":\s*(?P<rest>.+)$"
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _previous_tag() -> str:
    """Return the most recent `vX.Y.Z` tag, or `v0.0.0` if there is none."""
    try:
        # `--abbrev=0` returns the tag name only (no commits-since suffix).
        # `--match 'v*.*.*'` keeps us within SemVer-shaped tags so test or
        # nightly tags (e.g. `v0.0.0-test`) don't anchor the search.
        return _git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*")
    except subprocess.CalledProcessError:
        return "v0.0.0"


def _commits_since(tag: str) -> list[Commit]:
    """Walk `tag..HEAD`. If `tag` is the placeholder `v0.0.0`, walk all history."""
    spec = "HEAD" if tag == "v0.0.0" else f"{tag}..HEAD"
    raw = _git("log", spec, "--no-merges", "--pretty=format:%H%x09%h%x09%s")
    if not raw:
        return []

    commits: list[Commit] = []
    for line in raw.splitlines():
        sha, short, subject = line.split("\t", 2)
        pr_match = _PR_RE.search(subject)
        pr = f"#{pr_match.group(1)}" if pr_match else None
        clean_subject = _PR_RE.sub("", subject).strip()

        m = _SUBJECT_RE.match(clean_subject)
        if m:
            ctype = m.group("type").lower()
            scope = m.group("scope")
            breaking = bool(m.group("bang"))
            # Strip the conventional-commit prefix so the rendered subject
            # is not doubled (`**voice:** feat(voice): …`).
            display_subject = m.group("rest").strip()
        else:
            ctype = "other"
            scope = None
            breaking = False
            display_subject = clean_subject

        # `BREAKING CHANGE` in the body is also a major signal. We don't have
        # the body here; in practice repo convention uses `feat!:` / `fix!:`.

        commits.append(
            Commit(
                sha=sha,
                short=short,
                subject=display_subject,
                ctype=ctype,
                scope=scope,
                breaking=breaking,
                pr=pr,
            )
        )
    return commits


# User-visible types in priority order. `security` is a project-specific
# alias (also matched as `fix(security): …` via scope below).
_USER_VISIBLE = {"feat", "fix", "perf", "security", "revert", "refactor"}
_INVISIBLE = {"chore", "docs", "test", "ci", "build", "style"}


def _is_security(c: Commit) -> bool:
    return c.ctype == "security" or (c.scope or "").lower() == "security"


def _is_dependency(c: Commit) -> bool:
    return c.ctype == "chore" and (c.scope or "").startswith("deps")


def _decide_bump(commits: list[Commit]) -> str:
    has_user_visible = False
    has_feat = False
    has_breaking = False
    has_dep_bump = False

    for c in commits:
        if c.breaking:
            has_breaking = True
        if c.ctype == "feat":
            has_feat = True
            has_user_visible = True
        elif c.ctype in _USER_VISIBLE:
            has_user_visible = True
        elif _is_dependency(c):
            has_dep_bump = True

    if has_breaking:
        return "major"
    if has_feat:
        return "minor"
    if has_user_visible:
        return "patch"
    # Dependency-only days still produce a patch release so security audits
    # have a tagged anchor to point at.
    if has_dep_bump:
        return "patch"
    return "none"


def _bump_version(prev: str, bump: str) -> str:
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", prev)
    if not m:
        # If the previous tag is not strict SemVer (e.g. v2.0.0-beta), fall
        # back to v0.1.0 so the workflow does not silently regress.
        return "v0.1.0"
    major, minor, patch = (int(x) for x in m.groups())
    if bump == "major":
        return f"v{major + 1}.0.0"
    if bump == "minor":
        return f"v{major}.{minor + 1}.0"
    if bump == "patch":
        return f"v{major}.{minor}.{patch + 1}"
    return prev


_HEADINGS: "OrderedDict[str, str]" = OrderedDict(
    [
        ("breaking", "## ⚠️  Breaking changes"),
        ("feat", "## 🚀 Features"),
        ("fix", "## 🐛 Bug fixes"),
        ("security", "## 🔒 Security"),
        ("perf", "## ⚡ Performance"),
        ("refactor", "## 🧹 Refactors"),
        ("revert", "## ⏪ Reverts"),
        ("deps", "## 📦 Dependencies"),
        ("other", "## 🛠 Other"),
    ]
)


def _bucket(c: Commit) -> str:
    if c.breaking:
        return "breaking"
    if _is_security(c):
        return "security"
    if _is_dependency(c):
        return "deps"
    if c.ctype in {"feat", "fix", "perf", "refactor", "revert"}:
        return c.ctype
    if c.ctype in _INVISIBLE:
        return "other"
    return "other"


def _format_commit(c: Commit) -> str:
    scope = f"**{c.scope}:** " if c.scope and c.scope.lower() != "security" else ""
    pr = f" ({c.pr})" if c.pr else ""
    return f"- {scope}{c.subject} (`{c.short}`){pr}"


def _render_notes(prev: str, nxt: str, commits: list[Commit]) -> str:
    buckets: dict[str, list[Commit]] = {key: [] for key in _HEADINGS}
    for c in commits:
        buckets[_bucket(c)].append(c)

    lines: list[str] = []
    for key, heading in _HEADINGS.items():
        if not buckets[key]:
            continue
        lines.append(heading)
        lines.append("")
        for c in buckets[key]:
            lines.append(_format_commit(c))
        lines.append("")

    if not lines:
        lines.append("_No user-visible changes._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**Full Changelog**: {REPO_URL}/compare/{prev}...{nxt}")
    lines.append("")
    lines.append(
        "_Auto-generated by `.github/workflows/auto-release.yml` from Conventional "
        "Commits. Add `[skip release]` to a commit subject to skip the next cut, "
        "or run a manually-signed `git tag -s vX.Y.Z` to trigger the heavy "
        "`release.yml` pipeline (SBOM / Cosign / SLSA provenance)._"
    )
    return "\n".join(lines)


def _write_output(**kv: str) -> None:
    """Write key=value lines to $GITHUB_OUTPUT (or stdout when running locally)."""
    sink = os.environ.get("GITHUB_OUTPUT")
    target = open(sink, "a") if sink else sys.stdout
    try:
        for key, value in kv.items():
            target.write(f"{key}={value}\n")
    finally:
        if sink:
            target.close()


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"plan", "notes"}:
        sys.stderr.write("usage: auto_release.py {plan|notes}\n")
        return 2

    mode = sys.argv[1]
    prev = _previous_tag()
    commits = _commits_since(prev)
    bump = _decide_bump(commits)
    nxt = _bump_version(prev, bump) if bump != "none" else prev

    if mode == "plan":
        _write_output(prev_tag=prev, next_tag=nxt, bump=bump)
        return 0

    # mode == "notes"
    sys.stdout.write(_render_notes(prev, nxt, commits))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
