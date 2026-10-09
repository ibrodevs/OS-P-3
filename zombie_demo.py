#!/usr/bin/env python3
"""Create a zombie process long enough to inspect it with ps."""

from __future__ import annotations

import os
import subprocess
import time


def main() -> None:
    parent_pid = os.getpid()
    child_pid = os.fork()

    if child_pid == 0:
        print(f"[child] PID={os.getpid()} exits immediately", flush=True)
        os._exit(0)

    print(f"[parent] PID={parent_pid}, child PID={child_pid}", flush=True)
    print("[parent] not calling waitpid yet, so the child becomes a zombie", flush=True)
    time.sleep(1)

    print("\nps while child is a zombie:", flush=True)
    subprocess.run(
        [
            "ps",
            "-o",
            "pid,ppid,state,stat,cmd",
            "-p",
            f"{parent_pid},{child_pid}",
        ],
        check=False,
    )

    print("\n[parent] keeping zombie visible for 10 seconds...", flush=True)
    time.sleep(10)
    waited_pid, status = os.waitpid(child_pid, 0)
    print(f"[parent] waitpid({waited_pid}) collected status={status}; zombie is gone")


if __name__ == "__main__":
    main()
