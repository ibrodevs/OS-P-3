#!/usr/bin/env python3
"""Create an orphan and show which process adopts it on this Linux system."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def process_name(pid: int) -> str:
    try:
        return (Path("/proc") / str(pid) / "comm").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"


def main() -> None:
    original_parent = os.getpid()
    child_pid = os.fork()

    if child_pid > 0:
        print(
            f"[parent] PID={original_parent} created child PID={child_pid} and exits now",
            flush=True,
        )
        os._exit(0)

    child_pid = os.getpid()
    before = os.getppid()
    print(
        f"[child] PID={child_pid}; PPID just after fork={before} ({process_name(before)})",
        flush=True,
    )

    # Give the original parent time to terminate and Linux time to re-parent
    # this child to a configured subreaper or to PID 1.
    time.sleep(2)
    adopter = os.getppid()
    adopter_name = process_name(adopter)

    print(
        f"[child] original parent is gone; new PPID={adopter} ({adopter_name})",
        flush=True,
    )
    print("\nps after re-parenting:", flush=True)
    subprocess.run(
        ["ps", "-o", "pid,ppid,state,stat,cmd", "-p", f"{child_pid},{adopter}"],
        check=False,
    )
    print(
        f"\nAdopter on this run: PID {adopter} ({adopter_name}). "
        "If this is not PID 1, it is typically a configured subreaper.",
        flush=True,
    )


if __name__ == "__main__":
    main()
