"""Logged-in user sessions, from systemd-logind with `who` as fallback.

logind reports sessions (not terminals), so terminals inside one desktop add
nothing, and it sees Wayland desktops that never write utmp. `who` is used
only when logind cannot be queried.
"""
import re
import subprocess
import time
from collections import namedtuple

from . import log

TIMEOUT = 2
DESKTOP_TYPES = {"x11", "wayland", "mir"}
LIVE_STATES = {"active", "online"}
EXCLUDED_ACCOUNTS = {"gdm", "gdm-greeter", "lightdm", "sddm", "nobody"}
EXCLUDED_PREFIXES = ("gdm-greeter-",)
PROPERTIES = ("Id", "Name", "Type", "Class", "State", "Remote", "RemoteHost", "Service", "TTY")

# kind is "desktop", "ssh" or "tty"; remote is the SSH client address or None.
Session = namedtuple("Session", "user kind remote count")


def _excluded(user):
    return not user or user in EXCLUDED_ACCOUNTS or user.startswith(EXCLUDED_PREFIXES)


def _run(args, run):
    """Return stdout of a successful command, or None."""
    try:
        proc = run(args, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def parse_show_session(text):
    """Parse `loginctl show-session -p ...` output (records separated by blank lines)."""
    records, current = [], {}
    for line in text.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = value.strip()
    if current:
        records.append(current)
    return records


def classify_logind(record):
    """Return (user, kind, remote) for a reportable session, or None."""
    user = record.get("Name", "")
    if record.get("Class") != "user" or record.get("State") not in LIVE_STATES or _excluded(user):
        return None
    if record.get("Type") in DESKTOP_TYPES:
        return user, "desktop", None
    if record.get("Remote") == "yes" or record.get("Service") == "sshd":
        return user, "ssh", record.get("RemoteHost") or None
    return user, "tty", None


def _from_logind(run):
    listing = _run(["loginctl", "list-sessions", "--no-legend"], run)
    if listing is None:
        return None
    ids = [line.split()[0] for line in listing.splitlines() if line.split()]
    if not ids:
        return []
    args = ["loginctl", "show-session", *ids]
    for prop in PROPERTIES:
        args += ["-p", prop]
    shown = _run(args, run)
    if shown is None:
        return None
    return [s for s in map(classify_logind, parse_show_session(shown)) if s]


def classify_who(line):
    """Return (user, kind, remote) for one `who` line, or None.

    Examples: "alice pts/0 2026-10-11 12:00 (203.0.113.9)" -> ssh,
    "bob tty3 ..." -> tty, "alice :0 ... (:0)" or "alice seat0 ..." -> desktop.
    A pts line without a remote host is a terminal inside a desktop and is dropped.
    """
    fields = line.split()
    if len(fields) < 2:
        return None
    user, tty = fields[0], fields[1]
    if _excluded(user):
        return None
    match = re.search(r"\((.*)\)\s*$", line)  # greedy: keeps "tmux(4242).%0" whole
    host = match.group(1).strip() if match else ""
    if tty.startswith(":") or tty.startswith("seat") or host.startswith(":"):
        return user, "desktop", None
    if tty.startswith("pts/"):
        if not host or host.startswith("tmux"):
            return None
        return user, "ssh", host
    if tty.startswith("tty"):
        return user, "tty", None
    return None


def _from_who(run):
    out = _run(["who"], run)
    if out is None:
        return None
    return [s for s in map(classify_who, out.splitlines()) if s]


def dedupe(sessions):
    """Group identical (user, kind, remote) entries, counting them; stable order."""
    counts = {}
    for key in sessions:
        counts[key] = counts.get(key, 0) + 1
    order = {"desktop": 0, "ssh": 1, "tty": 2}
    keys = sorted(counts, key=lambda k: (k[0], order.get(k[1], 9), k[2] or ""))
    return [Session(user, kind, remote, counts[(user, kind, remote)]) for user, kind, remote in keys]


def logged_in_users(run=subprocess.run):
    """Return the deduplicated list of interactive sessions (possibly empty)."""
    found = _from_logind(run)
    if found is None:
        found = _from_who(run)
    if found is None:
        log.warning("could not list logged-in users (loginctl and who both failed)")
        return []
    return dedupe(found)


def wait_for_session(user, remote=None, timeout=3.0, interval=0.5,
                     lister=logged_in_users, sleep=time.sleep, clock=time.monotonic):
    """Wait until a session for ``user`` (from ``remote``, if given) is listed.

    Used by the login hook, whose PAM step may run before logind registers the
    new session. Returns True if it appeared, False after ``timeout``.
    """
    deadline = clock() + timeout
    while True:
        if any(s.user == user and (remote is None or s.remote == remote) for s in lister()):
            return True
        if clock() >= deadline:
            return False
        sleep(interval)
