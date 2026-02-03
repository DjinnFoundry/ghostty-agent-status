#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROXY_SRC="$ROOT_DIR/scripts/codex_ghostty_title_proxy.py"
SNIPPET_TEMPLATE="$ROOT_DIR/zsh/ghostty-agent-status.zsh.template"

TARGET_DIR="${HOME}/.local/bin"
PROXY_TARGET="$TARGET_DIR/agent-ghostty-title-proxy"
LEGACY_PROXY_TARGET="$TARGET_DIR/codex-ghostty-title-proxy"
SHELL_RC="${ZDOTDIR:-$HOME}/.zshrc"

START_MARKER="# >>> ghostty-agent-status >>>"
END_MARKER="# <<< ghostty-agent-status <<<"
LEGACY_START_MARKER="# >>> codex-ghostty-status >>>"
LEGACY_END_MARKER="# <<< codex-ghostty-status <<<"

if [[ ! -f "$PROXY_SRC" ]]; then
  echo "Error: missing $PROXY_SRC"
  exit 1
fi

if [[ ! -f "$SNIPPET_TEMPLATE" ]]; then
  echo "Error: missing $SNIPPET_TEMPLATE"
  exit 1
fi

mkdir -p "$TARGET_DIR"
install -m 0755 "$PROXY_SRC" "$PROXY_TARGET"
if [[ -f "$LEGACY_PROXY_TARGET" && "$LEGACY_PROXY_TARGET" != "$PROXY_TARGET" ]]; then
  rm -f "$LEGACY_PROXY_TARGET"
fi

mkdir -p "$(dirname "$SHELL_RC")"
touch "$SHELL_RC"

tmp_snippet="$(mktemp)"
tmp_rc="$(mktemp)"

trap 'rm -f "$tmp_snippet" "$tmp_rc"' EXIT

sed "s|__PROXY_PATH__|$PROXY_TARGET|g" "$SNIPPET_TEMPLATE" > "$tmp_snippet"

awk -v start="$START_MARKER" -v end="$END_MARKER" -v legacy_start="$LEGACY_START_MARKER" -v legacy_end="$LEGACY_END_MARKER" '
  $0 == start || $0 == legacy_start { in_block=1; next }
  $0 == end || $0 == legacy_end   { in_block=0; next }
  !in_block   { print }
' "$SHELL_RC" > "$tmp_rc"

# Keep spacing readable.
if [[ -s "$tmp_rc" ]]; then
  printf "\n" >> "$tmp_rc"
fi
cat "$tmp_snippet" >> "$tmp_rc"
printf "\n" >> "$tmp_rc"

mv "$tmp_rc" "$SHELL_RC"

echo "Installed!"
echo "- Proxy: $PROXY_TARGET"
echo "- Shell rc updated: $SHELL_RC"
echo "- Wrapped commands: codex, claude, claude-code, opencode"
echo ""
echo "Next: run 'source $SHELL_RC' or open a new Ghostty tab/window."
