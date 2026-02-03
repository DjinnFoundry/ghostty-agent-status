# codex-ghostty-status

Tiny `zsh` wrapper for `codex` that updates your Ghostty tab/header title with project + status.

Title format:

`<project> - codex - <status>`

Status states:

- `🟢 done` (Codex is waiting for your input)
- `🟡 working` (Codex is actively running)
- `🔴 approval` (Codex appears to be asking for confirmation)

## Why

When you have many Ghostty tabs, seeing only `codex` is low-context. This keeps the tab title meaningful by showing the current project and Codex state.

## Requirements

- macOS/Linux
- `zsh`
- [Ghostty](https://ghostty.org)
- `codex` CLI in `PATH`
- `python3`

## Install (easy)

```bash
git clone https://github.com/djinn/codex-ghostty-status.git
cd codex-ghostty-status
./scripts/install.sh
source ~/.zshrc
```

Open a new Ghostty tab/window (or run `source ~/.zshrc`) and run `codex`.

## Publish to GitHub (maintainer)

If you want to publish this repo to an org/user (default: `djinn`):

```bash
./scripts/publish.sh djinn codex-ghostty-status public
```

Prereqs:

- `gh auth login -h github.com` already done
- permission to create repos in the target org

## Uninstall

```bash
cd codex-ghostty-status
./scripts/uninstall.sh
```

## How it works

- Installs a proxy script at `~/.local/bin/codex-ghostty-title-proxy`
- Injects a small `codex()` function into your `~/.zshrc`
- Runs Codex inside a PTY and emits OSC title updates (`OSC 2`) for Ghostty

## Notes

- `🔴 approval` is heuristic-based (best effort from terminal output patterns).
- If `python3` is not available, the wrapper falls back to normal `codex` execution.
- Existing snippet is updated in place if you run install multiple times.

## Manual install (no git)

After this repo is public, you can also do:

```bash
curl -fsSL https://raw.githubusercontent.com/djinn/codex-ghostty-status/main/scripts/install.sh | bash
```

## License

MIT
