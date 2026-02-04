#!/usr/bin/env python3
"""Run an AI CLI in a PTY and update Ghostty title with status emojis."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import signal
import sys
import termios
import time
import tty

STATE_LABELS = {
    "working": "\U0001F7E1 working",      # yellow
    "waiting": "\U0001F7E2 done",         # green
    "approval": "\U0001F534 approval",    # red
}

COMMON_APPROVAL_HINTS = (
    "approval",
    "approve",
    "confirm",
)

AGENT_APPROVAL_HINTS = {
    "codex": (
        "allow codex to",
        "apply proposed code changes",
        "enable full access",
        "allow writes under this root",
        "yes, continue anyway",
        "go back without enabling full access",
        "acceptforsession",
    ),
    "claude": (
        # Permission prompts
        "do you want to proceed",
        "yes, and don't ask again",
        "tell claude what to do",
        "bash command",
        "edit file",
        "write to file",
        "allow tool",
        # Older/alternative prompts
        "permission mode",
        "bypass permissions",
        "allow dangerously skip permissions",
        "allow this action",
        "allow this command",
        "trust this directory",
    ),
    "claude-code": (
        # Permission prompts
        "do you want to proceed",
        "yes, and don't ask again",
        "tell claude what to do",
        "bash command",
        "edit file",
        "write to file",
        "allow tool",
        # Older/alternative prompts
        "permission mode",
        "bypass permissions",
        "allow dangerously skip permissions",
        "allow this action",
        "allow this command",
        "trust this directory",
    ),
    "opencode": (
        "permission denied",
        "continue anyway",
        "security warnings found",
        "cannot prompt for confirmation",
    ),
}

INTERACTION_HINTS = (
    " yes",
    " no",
    "y/n",
    "[y/n]",
    "[y/n]",
    "allow once",
    "allow always",
    "accept",
    "reject",
    "deny",
    "decline",
    "continue",
    "confirm",
)

CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
OSC_TITLE_RE = re.compile(rb"\x1b\]2;[^\x07]*(?:\x07|\x1b\\)")
CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]+")

# Keys that indicate user is responding to a prompt (not just typing)
RESPONSE_KEYS = (
    b"\r",      # Enter
    b"\n",      # Newline
    b"y",       # Yes
    b"Y",
    b"n",       # No
    b"N",
    b"1",       # Numbered options
    b"2",
    b"3",
    b"4",
)


def strip_osc_title(data: bytes) -> bytes:
    """Remove OSC 2 (set title) sequences from output to prevent agent from overwriting our title."""
    return OSC_TITLE_RE.sub(b"", data)


def title_agent_name(cmd: str) -> str:
    base = os.path.basename(cmd)
    if base in ("claude", "claude-code"):
        return "claude-code"
    if base in ("codex", "opencode"):
        return base
    return base or "agent"


def set_title(project: str, agent_name: str, state: str) -> None:
    label = STATE_LABELS.get(state, STATE_LABELS["waiting"])
    title = f"{project} - {agent_name} - {label}"
    sys.stdout.write(f"\033]2;{title}\a")
    sys.stdout.flush()


def normalize(chunk: bytes) -> str:
    text = chunk.decode("utf-8", errors="ignore").lower()
    text = OSC_RE.sub("", text)
    text = CSI_RE.sub("", text)
    text = CTRL_RE.sub(" ", text)
    return " ".join(text.split())


def copy_winsize(src_fd: int, dst_fd: int) -> None:
    try:
        winsz = fcntl.ioctl(src_fd, termios.TIOCGWINSZ, b"\x00" * 8)
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, winsz)
    except OSError:
        pass


def exit_code_from_wait_status(wait_status: int) -> int:
    if os.WIFEXITED(wait_status):
        return os.WEXITSTATUS(wait_status)
    if os.WIFSIGNALED(wait_status):
        return 128 + os.WTERMSIG(wait_status)
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        os.execvp("codex", ["codex"])

    project = CTRL_RE.sub("", sys.argv[1]) or "/"

    # New mode: <project> <command> [args...]
    # Backward-compatible mode: <project> [codex args...]
    if len(sys.argv) >= 3 and not sys.argv[2].startswith("-"):
        command = sys.argv[2]
        command_args = sys.argv[3:]
    else:
        command = "codex"
        command_args = sys.argv[2:]

    agent_name = title_agent_name(command)
    command_base = os.path.basename(command)
    approval_hints = COMMON_APPROVAL_HINTS + AGENT_APPROVAL_HINTS.get(command_base, ())
    cmd = [command, *command_args]

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    if not (os.isatty(stdin_fd) and os.isatty(stdout_fd)):
        os.execvp(cmd[0], cmd)

    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            os.execvp(cmd[0], cmd)
        except Exception:
            os._exit(127)

    state = "working"
    window = ""
    last_output = time.monotonic()
    last_title_refresh = time.monotonic()
    child_exited = False
    status = 1

    copy_winsize(stdin_fd, master_fd)
    set_title(project, agent_name, state)

    def on_winch(_signum, _frame):
        copy_winsize(stdin_fd, master_fd)
        if not child_exited:
            try:
                os.kill(pid, signal.SIGWINCH)
            except OSError:
                pass

    signal.signal(signal.SIGWINCH, on_winch)

    old_tty = termios.tcgetattr(stdin_fd)
    try:
        tty.setraw(stdin_fd)
        while True:
            now = time.monotonic()
            if not child_exited and state != "approval" and now - last_output > 1.4:
                if state != "waiting":
                    state = "waiting"
                    set_title(project, agent_name, state)
                    last_title_refresh = now

            # Refresh title periodically to recover from agent overwrites
            if now - last_title_refresh > 2.0:
                set_title(project, agent_name, state)
                last_title_refresh = now

            watched = [master_fd]
            if not child_exited:
                watched.append(stdin_fd)

            ready, _, _ = select.select(watched, [], [], 0.15)

            if master_fd in ready:
                try:
                    data = os.read(master_fd, 65536)
                except OSError:
                    data = b""

                if data:
                    # Strip OSC title sequences to prevent agent from overwriting our title
                    filtered_data = strip_osc_title(data)
                    os.write(stdout_fd, filtered_data)
                    last_output = time.monotonic()

                    normalized = normalize(data)
                    if normalized:
                        window = (window + " " + normalized)[-4000:]
                        needs_approval = any(hint in window for hint in approval_hints) and any(
                            token in window for token in INTERACTION_HINTS
                        )
                        if needs_approval:
                            if state != "approval":
                                state = "approval"
                                set_title(project, agent_name, state)
                                last_title_refresh = time.monotonic()
                        elif state != "approval":
                            if state != "working":
                                state = "working"
                                set_title(project, agent_name, state)
                                last_title_refresh = time.monotonic()
                elif child_exited:
                    break

            if not child_exited and stdin_fd in ready:
                try:
                    incoming = os.read(stdin_fd, 65536)
                except OSError:
                    incoming = b""

                if incoming:
                    os.write(master_fd, incoming)
                    # Only transition from approval to working when user sends a response key
                    # (not just any keystroke while typing a new prompt)
                    if state == "approval" and any(key in incoming for key in RESPONSE_KEYS):
                        state = "working"
                        window = ""  # Clear window to reset approval detection
                        set_title(project, agent_name, state)
                        last_title_refresh = time.monotonic()
                else:
                    break

            if not child_exited:
                try:
                    waited_pid, waited_status = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    waited_pid, waited_status = pid, 1 << 8

                if waited_pid == pid:
                    child_exited = True
                    status = exit_code_from_wait_status(waited_status)
                    if state != "waiting":
                        state = "waiting"
                        set_title(project, agent_name, state)
                        last_title_refresh = time.monotonic()
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        try:
            os.close(master_fd)
        except OSError:
            pass

    return status


if __name__ == "__main__":
    raise SystemExit(main())
