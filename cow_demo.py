#!/usr/bin/env python3
"""Demonstrate fork() copy-on-write with a large inherited Python list."""

from __future__ import annotations

import argparse
import os
import resource
import time
from pathlib import Path

PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")


def memory_stats_kb() -> dict[str, int]:
    """Read process memory counters from /proc/self/smaps_rollup."""
    wanted = {
        "Rss",
        "Pss",
        "Shared_Clean",
        "Shared_Dirty",
        "Private_Clean",
        "Private_Dirty",
    }
    result = {key: 0 for key in wanted}
    try:
        with Path("/proc/self/smaps_rollup").open(encoding="utf-8") as f:
            for line in f:
                key, _, value = line.partition(":")
                if key in wanted:
                    result[key] = int(value.split()[0])
    except OSError:
        # VmRSS is enough for the required RSS reading; the extra fields are
        # best-effort because very old kernels may not expose smaps_rollup.
        with Path("/proc/self/status").open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    result["Rss"] = int(line.split()[1])
                    break
    return result


def print_stats(label: str) -> None:
    stats = memory_stats_kb()
    faults = resource.getrusage(resource.RUSAGE_SELF).ru_minflt
    print(
        f"{label}: RSS={stats['Rss']} kB, PSS={stats['Pss']} kB, "
        f"Shared_Dirty={stats['Shared_Dirty']} kB, "
        f"Private_Dirty={stats['Private_Dirty']} kB, minor_faults={faults}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstrate lazy copy-on-write after fork")
    parser.add_argument(
        "--size-mb",
        type=int,
        default=64,
        help="approximate payload size of the inherited list (default: 64 MiB)",
    )
    args = parser.parse_args()
    if args.size_mb <= 0:
        parser.error("--size-mb must be greater than zero")

    page_count = args.size_mb * 1024 * 1024 // PAGE_SIZE
    big_list = [bytearray(PAGE_SIZE) for _ in range(page_count)]

    # Touch every page in the parent so the pages are resident before fork().
    for block in big_list:
        block[0] = 1

    print(
        f"Parent PID={os.getpid()} prepared {len(big_list)} blocks "
        f"(~{args.size_mb} MiB payload)",
        flush=True,
    )

    pid = os.fork()
    if pid == 0:
        print(f"Child PID={os.getpid()} inherited the list from parent", flush=True)
        print_stats("child before writes")
        time.sleep(0.5)

        # Each write forces the kernel to copy the corresponding shared page
        # for the child instead of copying the whole list immediately at fork.
        for block in big_list:
            block[0] ^= 1

        print_stats("child after writes ")
        os._exit(0)

    os.waitpid(pid, 0)
    print("Parent: child finished; original list is unchanged in the parent.", flush=True)


if __name__ == "__main__":
    main()
