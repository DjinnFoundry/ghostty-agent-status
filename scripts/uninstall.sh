#!/usr/bin/env bash
set -euo pipefail

SHELL_RC="${ZDOTDIR:-$HOME}/.zshrc"
PROXY_TARGET="${HOME}/.local/bin/agent-ghostty-title-proxy"
LEGACY_PROXY_TARGET="${HOME}/.local/bin/codex-ghostty-title-proxy"

START_MARKER="# >>> codex-ghostty-status >>>"
END_MARKER="# <<< codex-ghostty-status <<<"

if [[ -f "$SHELL_RC" ]]; then
  tmp_rc="$(mktemp)"
  trap 'rm -f "$tmp_rc"' EXIT

  awk -v start="$START_MARKER" -v end="$END_MARKER" '
    $0 == start { in_block=1; next }
    $0 == end   { in_block=0; next }
    !in_block   { print }
  ' "$SHELL_RC" > "$tmp_rc"

  mv "$tmp_rc" "$SHELL_RC"
  echo "Removed snippet from: $SHELL_RC"
else
  echo "No shell rc found at: $SHELL_RC"
fi

if [[ -f "$PROXY_TARGET" ]]; then
  rm -f "$PROXY_TARGET"
  echo "Removed proxy: $PROXY_TARGET"
fi

if [[ -f "$LEGACY_PROXY_TARGET" ]]; then
  rm -f "$LEGACY_PROXY_TARGET"
  echo "Removed legacy proxy: $LEGACY_PROXY_TARGET"
fi

echo "Uninstalled. Open a new terminal tab/window or run: source $SHELL_RC"
