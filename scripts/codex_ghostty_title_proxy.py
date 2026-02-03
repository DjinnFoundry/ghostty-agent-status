#!/usr/bin/env python3
"""Run codex in a PTY and update Ghostty title with status emojis."""

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

APPROVAL_HINTS = (
    "allow codex to",
    "approval",
    "approve",
    "apply proposed code changes",
    "enable full access",
    "allow writes under this root",
    "yes, continue anyway",
    "go back without enabling full access",
    "acceptforsession",
    "decline",
)

INTERACTION_HINTS = (" yes", " no", "continue", "decline", "approval", "confirm")

CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]+")


def set_title(project: str, state: str) -> None:
    label = STATE_LABELS.get(state, STATE_LABELS["waiting"])
    title = f"{project} - codex - {label}"
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
    codex_args = sys.argv[2:]
    cmd = ["codex", *codex_args]

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
    child_exited = False
    status = 1

    copy_winsize(stdin_fd, master_fd)
    set_title(project, state)

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
                    set_title(project, state)

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
                    os.write(stdout_fd, data)
                    last_output = time.monotonic()

                    normalized = normalize(data)
                    if normalized:
                        window = (window + " " + normalized)[-4000:]
                        needs_approval = any(hint in window for hint in APPROVAL_HINTS) and any(
                            token in window for token in INTERACTION_HINTS
                        )
                        if needs_approval:
                            if state != "approval":
                                state = "approval"
                                set_title(project, state)
                        elif state != "approval":
                            if state != "working":
                                state = "working"
                                set_title(project, state)
                elif child_exited:
                    break

            if not child_exited and stdin_fd in ready:
                try:
                    incoming = os.read(stdin_fd, 65536)
                except OSError:
                    incoming = b""

                if incoming:
                    os.write(master_fd, incoming)
                    if state == "approval":
                        state = "working"
                        set_title(project, state)
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
                        set_title(project, state)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        try:
            os.close(master_fd)
        except OSError:
            pass

    return status


if __name__ == "__main__":
    raise SystemExit(main())
