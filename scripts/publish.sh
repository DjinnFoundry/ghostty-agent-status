#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORG="${1:-djinn}"
REPO_NAME="${2:-codex-ghostty-status}"
VISIBILITY="${3:-public}" # public|private

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI is required. Install from https://cli.github.com/"
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "Error: gh is not authenticated. Run: gh auth login -h github.com"
  exit 1
fi

case "$VISIBILITY" in
  public) visibility_flag="--public" ;;
  private) visibility_flag="--private" ;;
  *)
    echo "Error: visibility must be 'public' or 'private'"
    exit 1
    ;;
esac

if git -C "$ROOT_DIR" remote get-url origin >/dev/null 2>&1; then
  echo "Remote 'origin' already exists. Pushing current branch..."
  git -C "$ROOT_DIR" push -u origin main
  echo "Done."
  exit 0
fi

echo "Creating GitHub repo: $ORG/$REPO_NAME ($VISIBILITY)"
gh repo create "$ORG/$REPO_NAME" "$visibility_flag" --source="$ROOT_DIR" --remote=origin --push

echo "Done: https://github.com/$ORG/$REPO_NAME"
