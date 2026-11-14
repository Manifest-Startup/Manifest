#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Starting Manifest (backend + frontend)..."

# Open app/docs once services are reachable.
(
  for _ in {1..120}; do
    if nc -z 127.0.0.1 3000 && nc -z 127.0.0.1 8000; then
      if command -v open >/dev/null 2>&1; then
        open "http://localhost:3000" || true
        open "http://localhost:8000/docs" || true
      fi
      exit 0
    fi
    sleep 1
  done
  echo "Timed out waiting for services. Check startup logs above."
) &

python3 scripts/start_app.py
