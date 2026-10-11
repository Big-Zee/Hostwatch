"""Top processes by current CPU use, sampled from /proc.

Two snapshots of every process's utime+stime, taken SAMPLE_SECONDS apart,
give CPU use *now* (a single `ps` reading would be a lifetime average).
CPU % is relative to one core, as in `top`, so it can exceed 100 on
multi-core machines. Command lines are never read.
"""
import mmap
import os
import time
from collections import namedtuple

try:
    import pwd
except ImportError:  # pragma: no cover - not available on Windows
    pwd = None

SAMPLE_SECONDS = 1.0
USER_WIDTH = 8
NAME_WIDTH = 15

Row = namedtuple("Row", "pid user cpu mem name")


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _ticks(proc_root, pid):
    """utime + stime of one process, from fields 14 and 15 of /proc/<pid>/stat."""
    stat = _read(os.path.join(proc_root, pid, "stat"))
    rest = stat[stat.rindex(")") + 1:].split()  # comm may contain spaces and ")"
    return int(rest[11]) + int(rest[12])


def _snapshot(proc_root):
    ticks = {}
    for name in os.listdir(proc_root):
        if name.isdigit():
            try:
                ticks[name] = _ticks(proc_root, name)
            except (OSError, ValueError, IndexError):
                pass  # exited or unreadable
    return ticks


def _mem_total_kb(proc_root):
    for line in _read(os.path.join(proc_root, "meminfo")).splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1])
    raise ValueError("MemTotal missing")


def _user(proc_root, pid):
    for line in _read(os.path.join(proc_root, pid, "status")).splitlines():
        if line.startswith("Uid:"):
            uid = int(line.split()[1])  # real UID
            if pwd is not None:
                try:
                    return pwd.getpwuid(uid).pw_name
                except KeyError:
                    pass
            return str(uid)
    return "?"


def _details(proc_root, pid, page_size, mem_total_kb):
    name = _read(os.path.join(proc_root, pid, "comm")).strip()
    rss_pages = int(_read(os.path.join(proc_root, pid, "statm")).split()[1])
    mem = rss_pages * page_size / (mem_total_kb * 1024) * 100 if mem_total_kb else 0.0
    return _user(proc_root, pid), mem, name


def top_processes(n=5, sample=SAMPLE_SECONDS, proc_root="/proc", own_pid=None,
                  sleep=time.sleep, clock=time.monotonic, clk_tck=None, page_size=None):
    """Return up to ``n`` Rows, busiest first (CPU %, then memory %)."""
    own = str(os.getpid() if own_pid is None else own_pid)
    if clk_tck is None:
        clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    page_size = page_size or mmap.PAGESIZE
    try:
        mem_total_kb = _mem_total_kb(proc_root)
        start, t0 = _snapshot(proc_root), clock()
        sleep(sample)
        end, t1 = _snapshot(proc_root), clock()
    except (OSError, ValueError):
        return []
    elapsed = max(t1 - t0, 1e-6)
    rows = []
    for pid in start.keys() & end.keys():  # skip processes that appeared or exited
        if pid == own:
            continue
        cpu = max(end[pid] - start[pid], 0) / (elapsed * clk_tck) * 100
        try:
            user, mem, name = _details(proc_root, pid, page_size, mem_total_kb)
        except (OSError, ValueError, IndexError):
            continue
        rows.append(Row(int(pid), user, cpu, mem, name))
    rows.sort(key=lambda r: (-r.cpu, -r.mem, r.pid))
    return rows[:n]


def _fit(text, width):
    return text if len(text) <= width else text[:width - 1] + "+"


def format_table(rows):
    """Fixed-width table in a code block, so columns align on mobile."""
    if not rows:
        return "```\n(no process data)\n```"
    lines = [f"{'PID':>7} {'USER':<{USER_WIDTH}} {'CPU%':>5} {'MEM%':>5}  NAME"]
    for r in rows:
        lines.append(f"{r.pid:>7} {_fit(r.user, USER_WIDTH):<{USER_WIDTH}} "
                     f"{r.cpu:>5.1f} {r.mem:>5.1f}  {_fit(r.name, NAME_WIDTH)}")
    return "```\n" + "\n".join(lines) + "\n```"
