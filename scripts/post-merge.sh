#!/bin/bash
set -e

# Post-merge hook: rebuild the frontend so the served bundle reflects
# any changes the just-merged task introduced.
#
# Why `npm ci` and not `npm install`:
#   `npm install` periodically trips the well-known npm optional-deps
#   bug (https://github.com/npm/cli/issues/4828) where platform-
#   specific Rollup binaries (e.g. `@rollup/rollup-linux-x64-gnu`) are
#   omitted from `node_modules` and the next `vite build` crashes
#   with `Cannot find module @rollup/rollup-linux-x64-gnu`. `npm ci`
#   wipes `node_modules` and re-installs strictly from the lockfile,
#   which sidesteps the bug deterministically.

echo "[post-merge] Installing frontend dependencies..."
cd frontend
if [ -f package-lock.json ]; then
  npm ci --legacy-peer-deps --no-fund --no-audit -q
else
  # Fallback for environments where the lockfile is missing — defensive
  # only; CI/SEC-074 lockfile-drift gate ensures it is normally present.
  npm install --legacy-peer-deps --no-fund --no-audit -q
fi

# Belt-and-braces workaround for npm/cli#4828: even `npm ci` periodically
# omits the platform-specific Rollup native binary from `node_modules`,
# causing `vite build` to crash with
# `Cannot find module @rollup/rollup-linux-x64-gnu`. Detect the gap and
# install the matching binary explicitly. The version is read from the
# already-installed `rollup` package so it always lines up with whatever
# the lockfile resolved.
ROLLUP_PKG=""
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)  ROLLUP_PKG="@rollup/rollup-linux-x64-gnu" ;;
  Linux-aarch64) ROLLUP_PKG="@rollup/rollup-linux-arm64-gnu" ;;
  Darwin-arm64)  ROLLUP_PKG="@rollup/rollup-darwin-arm64" ;;
  Darwin-x86_64) ROLLUP_PKG="@rollup/rollup-darwin-x64" ;;
esac
if [ -n "$ROLLUP_PKG" ] && [ ! -d "node_modules/${ROLLUP_PKG}" ]; then
  ROLLUP_VERSION=$(node -p "require('./node_modules/rollup/package.json').version" 2>/dev/null || echo "")
  if [ -n "$ROLLUP_VERSION" ]; then
    echo "[post-merge] Patching missing Rollup native binary: ${ROLLUP_PKG}@${ROLLUP_VERSION} (npm/cli#4828 workaround)"
    npm install --no-save --no-fund --no-audit -q "${ROLLUP_PKG}@${ROLLUP_VERSION}" || true
  fi
fi

echo "[post-merge] Building frontend..."
npm run build

echo "[post-merge] Done."
