#!/bin/bash
set -e

# Deployment build entry point (referenced from .replit `[deployment].build`).
# Mirrors the install/build logic in scripts/post-merge.sh so production
# deploys and post-merge rebuilds use the same Rollup-bug-resilient path.
#
# Why this is non-trivial:
#   `npm install` periodically trips the well-known npm optional-deps bug
#   (https://github.com/npm/cli/issues/4828) where platform-specific Rollup
#   native binaries (e.g. `@rollup/rollup-linux-x64-gnu`) are silently
#   omitted from `node_modules`, and the next `vite build` crashes with
#   `Cannot find module @rollup/rollup-linux-x64-gnu`. We:
#     1. Prefer `npm ci` (deterministic, lockfile-driven) when available.
#     2. After install, detect the platform and verify the matching
#        Rollup binary is present; if not, install it explicitly at the
#        version `rollup` itself resolved to.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/frontend"

echo "[build] Installing frontend dependencies..."
if [ -f package-lock.json ]; then
  npm ci --legacy-peer-deps --no-fund --no-audit
else
  npm install --legacy-peer-deps --no-fund --no-audit
fi

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
    echo "[build] Patching missing Rollup native binary: ${ROLLUP_PKG}@${ROLLUP_VERSION} (npm/cli#4828 workaround)"
    npm install --no-save --no-fund --no-audit "${ROLLUP_PKG}@${ROLLUP_VERSION}" || true
  fi
fi

echo "[build] Building frontend..."
npm run build

echo "[build] Done."
