#!/usr/bin/env python3
"""One local check command for Manifest: test what you changed, fast.

    python3 scripts/check.py            # files changed vs origin/main (+ uncommitted)
    python3 scripts/check.py --all      # every check, whole repo
    python3 scripts/check.py --install-hook   # run it automatically before `git push`

Only the areas you touched run, one after another (parallel test runners starve
each other and cause flaky Jest timeouts):
  python   ruff lint + format (pinned 0.6.9) on changed Python files
  backend  full pytest suite (~25 s)
  frontend jest --findRelatedTests on changed files, tsc --noEmit, eslint on changed files
  edge     node --test for the Cloudflare Worker
  mcp      pytest mcp_server/tests
  tooling  pytest tests (developer CLI + code graph)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = (
    str(ROOT / ".venv" / "bin" / "python")
    if (ROOT / ".venv" / "bin" / "python").exists()
    else sys.executable
)
RUFF = ["uvx", "-q", "ruff@0.6.9"] if shutil.which("uvx") else [PY, "-m", "ruff"]
LINTED_PY_ROOTS = ("backend/app/", "mcp_server/src/", "src/manifest_dev/")
FULL_BACKEND_TRIGGERS = (
    "backend/tests/conftest.py",
    "backend/pytest.ini",
    "backend/requirements.txt",
)


def sh(cmd: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def changed_files() -> list[str]:
    base = "origin/main"
    _, merge_base = sh(["git", "merge-base", "HEAD", base])
    files: set[str] = set()
    for cmd in (
        ["git", "diff", "--name-only", merge_base.strip() or base],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        files |= set(sh(cmd)[1].splitlines())
    return sorted(f for f in files if f and (ROOT / f).exists())


# --------------------------------------------------------------------------- checks
def check_python(files: list[str]) -> tuple[int, str]:
    targets = (
        [f for f in files if f.endswith(".py") and f.startswith(LINTED_PY_ROOTS)]
        if files
        else list(LINTED_PY_ROOTS)
    )
    if not targets:
        return 0, "no linted Python changed"
    code, out = sh([*RUFF, "check", *targets])
    code2, out2 = sh([*RUFF, "format", "--check", *targets])
    return code or code2, "\n".join(x for x in (out, out2) if x)


def check_backend(files: list[str]) -> tuple[int, str]:
    # The whole suite takes ~25 s and most tests boot app.main, so targeting a
    # subset buys almost nothing; run everything whenever backend code changed.
    if files and not any(f.startswith("backend/") for f in files):
        return 0, "backend unchanged"
    cmd = [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-o", "addopts="]
    code, out = sh(cmd, ROOT / "backend")
    return code, "\n".join(out.splitlines()[-15:])


def check_frontend(files: list[str]) -> tuple[int, str]:
    fe = [f.removeprefix("frontend/") for f in files if f.startswith("frontend/src/")]
    if files and not fe:
        return 0, "no frontend source changed"
    lintable = [f for f in fe if f.endswith((".ts", ".tsx", ".js", ".jsx"))]
    tasks = {
        "jest": ["npx", "jest", "--silent", "--passWithNoTests", "--maxWorkers=50%"]
        + (["--findRelatedTests", *fe] if fe else []),
        "tsc": ["npx", "tsc", "--noEmit", "-p", "."],
        "eslint": ["npx", "eslint", *(lintable or ["src"])],
    }
    worst, lines = 0, []
    for name, cmd in tasks.items():
        code, out = sh(cmd, ROOT / "frontend")
        worst = max(worst, code)
        detail = [
            ln
            for ln in out.splitlines()
            if ln.startswith(("Tests:", "FAIL")) or "error" in ln.lower()
        ]
        lines.append(f"{name}: {'ok' if code == 0 else 'FAILED'}")
        if code:
            lines += detail[-12:]
    return worst, "\n".join(lines)


def check_edge(files: list[str]) -> tuple[int, str]:
    if files and not any(f.startswith("deploy/cloudflare/") for f in files):
        return 0, "edge Worker unchanged"
    code, out = sh(["npm", "test", "--silent"], ROOT / "deploy" / "cloudflare")
    return code, "\n".join(
        ln for ln in out.splitlines() if ln.startswith(("# pass", "# fail", "not ok"))
    )


def check_mcp(files: list[str]) -> tuple[int, str]:
    if files and not any(f.startswith("mcp_server/") for f in files):
        return 0, "MCP server unchanged"
    code, out = sh(
        [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "mcp_server/tests"]
    )
    return code, out.splitlines()[-1] if out else ""


def check_tooling(files: list[str]) -> tuple[int, str]:
    if files and not any(f.startswith(("scripts/", "src/", "tests/")) for f in files):
        return 0, "tooling unchanged"
    code, out = sh([PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "tests"])
    return code, out.splitlines()[-1] if out else ""


CHECKS = {
    "python": check_python,
    "backend": check_backend,
    "frontend": check_frontend,
    "edge": check_edge,
    "mcp": check_mcp,
    "tooling": check_tooling,
}


def install_hook() -> int:
    hook = Path(sh(["git", "rev-parse", "--git-path", "hooks"])[1]) / "pre-push"
    hook = hook if hook.is_absolute() else ROOT / hook
    hook.write_text(
        "#!/bin/sh\n# Installed by scripts/check.py --install-hook. Skip once with: git push --no-verify\n"
        'exec python3 "$(git rev-parse --show-toplevel)/scripts/check.py"\n'
    )
    hook.chmod(0o755)
    print(f"pre-push hook installed at {hook}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true", help="run every check on the whole repo")
    ap.add_argument("--only", choices=CHECKS, nargs="+", help="run just these areas")
    ap.add_argument("--install-hook", action="store_true", help="run this before every git push")
    args = ap.parse_args()
    if args.install_hook:
        return install_hook()
    files = [] if args.all else changed_files()
    if not args.all and not files:
        print("Nothing changed vs origin/main. Use --all to check everything.")
        return 0
    names = args.only or list(CHECKS)
    print(
        f"Checking {'everything' if args.all else f'{len(files)} changed files'}: {', '.join(names)}"
    )
    start = time.perf_counter()
    results = {}
    for n in names:
        t0 = time.perf_counter()
        results[n] = (t0, CHECKS[n](files), time.perf_counter())
    failed = []
    for name, (t0, (code, out), t1) in results.items():
        status = "PASS" if code == 0 else "FAIL"
        print(f"\n{status}  {name:<9} {t1 - t0:5.1f}s")
        if out and (code or os.getenv("VERBOSE")):
            print("  " + out.replace("\n", "\n  "))
        elif out:
            print(f"  {out.splitlines()[-1]}")
        if code:
            failed.append(name)
    print(
        f"\n{'All checks passed' if not failed else 'FAILED: ' + ', '.join(failed)} in {time.perf_counter() - start:.1f}s"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
