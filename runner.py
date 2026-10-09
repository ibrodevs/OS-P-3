#!/usr/bin/env python3
"""Fork N children, exec a command in each, and report result and runtime."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time


def parse_args() -> tuple[int, list[str]]:
    parser = argparse.ArgumentParser(
        description=(
            "Create N child processes with fork(); each child starts the given "
            "command with exec()."
        )
    )
    parser.add_argument("N", type=int, help="number of child processes")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="command and its arguments (use -- before the command if needed)",
    )
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]

    if args.N <= 0:
        parser.error("N must be greater than zero")
    if not command:
        parser.error("a command is required")

    return args.N, command


def status_text(status: int) -> tuple[int, str]:
    if os.WIFEXITED(status):
        code = os.WEXITSTATUS(status)
        return code, f"exit code {code}"
    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        try:
            sig_name = signal.Signals(sig).name
        except ValueError:
            sig_name = str(sig)
        return 128 + sig, f"signal {sig} ({sig_name})"
    return status, f"raw wait status {status}"


def main() -> None:
    count, command = parse_args()
    started_at: dict[int, float] = {}

    for _ in range(count):
        start = time.monotonic()
        pid = os.fork()
        if pid == 0:
            try:
                os.execvp(command[0], command)
            except OSError as exc:
                print(f"exec failed: {exc}", file=sys.stderr, flush=True)
                os._exit(127)
        started_at[pid] = start

    remaining = set(started_at)
    results: dict[int, tuple[int, str, float]] = {}

    while remaining:
        pid, status = os.waitpid(-1, 0)
        if pid not in remaining:
            continue
        elapsed = time.monotonic() - started_at[pid]
        code, description = status_text(status)
        results[pid] = (code, description, elapsed)
        remaining.remove(pid)

    for pid in sorted(results):
        code, description, elapsed = results[pid]
        print(
            f"PID {pid}: return={code} ({description}), "
            f"runtime={elapsed:.3f} s"
        )


if __name__ == "__main__":
    main()
