#!/usr/bin/env python3
"""Print a process tree for the current user using only /proc."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

PROC = Path("/proc")


@dataclass
class ProcessInfo:
    pid: int
    ppid: int
    name: str
    state: str
    rss_kb: int


def read_status(pid: int) -> ProcessInfo | None:
    """Read the fields we need from /proc/<pid>/status.

    Processes may disappear while /proc is being scanned, so failures are
    expected and simply mean that process is skipped.
    """
    try:
        fields: dict[str, str] = {}
        with (PROC / str(pid) / "status").open(encoding="utf-8") as status_file:
            for line in status_file:
                key, _, value = line.partition(":")
                if key in {"Name", "State", "PPid", "Uid", "VmRSS"}:
                    fields[key] = value.strip()

        real_uid = int(fields["Uid"].split()[0])
        if real_uid != os.getuid():
            return None

        rss_kb = int(fields.get("VmRSS", "0 kB").split()[0])
        state = fields.get("State", "?").split()[0]
        return ProcessInfo(
            pid=pid,
            ppid=int(fields.get("PPid", "0")),
            name=fields.get("Name", "?"),
            state=state,
            rss_kb=rss_kb,
        )
    except (FileNotFoundError, ProcessLookupError, PermissionError, KeyError, ValueError):
        return None


def collect_processes() -> Dict[int, ProcessInfo]:
    processes: Dict[int, ProcessInfo] = {}
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        info = read_status(int(entry.name))
        if info is not None:
            processes[info.pid] = info
    return processes


def print_tree(processes: Dict[int, ProcessInfo]) -> None:
    children: Dict[int, List[int]] = {}
    for proc in processes.values():
        children.setdefault(proc.ppid, []).append(proc.pid)

    for pid_list in children.values():
        pid_list.sort()

    roots = sorted(
        pid for pid, proc in processes.items() if proc.ppid not in processes
    )

    def visit(pid: int, depth: int) -> None:
        proc = processes[pid]
        print(
            f"{'  ' * depth}{proc.name} "
            f"(PID={proc.pid}, state={proc.state}, RSS={proc.rss_kb} kB)"
        )
        for child_pid in children.get(pid, []):
            visit(child_pid, depth + 1)

    for root_pid in roots:
        visit(root_pid, 0)


def main() -> None:
    processes = collect_processes()
    if not processes:
        print("No processes for the current user were found.")
        return
    print_tree(processes)


if __name__ == "__main__":
    main()
