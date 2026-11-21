#!/bin/sh
# Manifest voice on this computer: talk to Claude Code or Codex from the Manifest app,
# with no API key. Installs the `manifest` CLI (from the public Manifest repo, with uv) and
# runs `manifest bridge` at login. Safe to run again: it updates and restarts the bridge.
#
#   curl -fsSL https://manifeststartup.com/voice.sh | sh
#
# The bridge listens on 127.0.0.1 only and answers only Manifest's own pages.
# Undo: manifest bridge --uninstall && uv tool uninstall manifest-mcp
set -eu

say() { printf '\033[1m%s\033[0m\n' "$*"; }

if command -v claude >/dev/null 2>&1; then
  agent="Claude Code"
elif command -v codex >/dev/null 2>&1; then
  agent="Codex"
else
  say "Manifest voice needs Claude Code or Codex on this computer first."
  echo "  Claude Code: https://claude.com/claude-code"
  echo "  Codex:       https://developers.openai.com/codex"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (Python tool installer)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  export PATH
fi

package="manifest-mcp"
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  package="manifest-mcp[natural-voice]"  # the natural voice: Kokoro on the Apple GPU
fi
say "Installing the Manifest CLI…"
uv tool install --force --quiet --python 3.12 \
  "${package} @ git+https://github.com/Manifest-Startup/Manifest#subdirectory=mcp_server"
PATH="$(uv tool dir --bin):$PATH"
export PATH

if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  # Download and try the natural voice now, so the first conversation doesn't wait for it.
  manifest bridge --check-voice || say "The natural voice didn't load; the browser's voice will speak. Run this again to retry."
fi

if [ "$(uname -s)" = "Darwin" ]; then
  say "Connecting Manifest voice to ${agent}…"
  manifest bridge --install
  say "Done. Go back to Manifest: voice connects by itself (the natural voice downloads once, ~330 MB)."
else
  say "Installed. Start it with: manifest bridge   (keep it running; voice connects by itself)"
fi
