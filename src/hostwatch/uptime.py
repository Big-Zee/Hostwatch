"""Boot-session ledger and the shared "uptime today" calculation.

The ledger (``uptime.json`` in /var/lib/hostwatch) is a JSON array of session
records: ``{"start": iso8601, "end": iso8601|null, "reason":
"clean"|"reboot"|"unclean"|null, "estimated": bool}``. An entry with "end":
null is still open (the currently running session, or one left open by a
crash before any boot closed it). Mutating writes go through a lock file and
an atomic temp-file-then-rename, mirroring the clean-shutdown marker in
state.py. Reads never need the lock: a reader only ever sees either the old
file or the fully written new one.

Every public function here is best-effort: on any I/O or data problem it
logs to the journal and returns a safe fallback (None, False, or an empty
result) instead of raising, so a ledger problem can never delay or fail a
boot, login, shutdown or heartbeat notification.
"""
import contextlib
import json
import os
import tempfile
import time
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from . import log, state

# Same directory (and the same override for tests) as the clean-shutdown
# marker in state.py; re-exported here so callers of this module don't need
# to import state.py just to find or override it.
STATE_DIR_ENV = state.STATE_DIR_ENV
LEDGER_NAME = "uptime.json"
LOCK_NAME = "uptime.lock"
LAST_ALIVE_NAME = "last_alive"

# Bounded so a lock held by another writer never delays boot/login/shutdown
# beyond their existing timeouts.
LOCK_RETRY_INTERVAL = 0.05
LOCK_BUDGET = 1.0

TodayUptime = namedtuple("TodayUptime", "seconds sessions estimated")


def _state_dir():
    return state._state_dir()


def _ledger_path():
    return os.path.join(_state_dir(), LEDGER_NAME)


def _lock_path():
    return os.path.join(_state_dir(), LOCK_NAME)


def _last_alive_path():
    return os.path.join(_state_dir(), LAST_ALIVE_NAME)


def _parse_time(text):
    """Parse an aware ISO 8601 timestamp, or return None if it is not one."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc)


def _format_time(moment):
    return moment.astimezone(timezone.utc).isoformat()


def _valid_entry(raw):
    """Return a normalized entry (datetimes, not strings), or None if unusable."""
    if not isinstance(raw, dict):
        return None
    start = _parse_time(raw.get("start"))
    if start is None:
        return None
    end = _parse_time(raw.get("end")) if raw.get("end") is not None else None
    reason = raw.get("reason") if isinstance(raw.get("reason"), str) else None
    return {"start": start, "end": end, "reason": reason, "estimated": bool(raw.get("estimated"))}


def load_ledger(path=None):
    """Return (entries, status): status is "ok", "absent" or "corrupt".

    A record that cannot be parsed is dropped rather than failing the whole
    read; only a file that cannot be opened or decoded at all is "corrupt".
    """
    path = path or _ledger_path()
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return [], "absent"
    except (OSError, ValueError):
        return [], "corrupt"
    if not isinstance(raw, list):
        return [], "corrupt"
    entries = [e for e in (_valid_entry(r) for r in raw) if e is not None]
    return entries, "ok"


def today_uptime(entries, current_session_start, now, tz=None):
    """Total time powered on today (local calendar day), per uptime-summary.

    ``entries`` are past, closed sessions (an entry with no "end" is still
    open and is ignored here; the caller passes the one currently running
    session explicitly as ``current_session_start``, or None to leave it
    out). A session is clipped to local midnight; one whose duration would
    be negative (clock moved backwards) is excluded rather than counted.
    ``tz`` defaults to the system timezone (per the uptime-summary spec);
    tests pass an explicit zone so the result does not depend on the host
    running the tests.
    """
    local_midnight = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = local_midnight.astimezone(timezone.utc)

    sessions = [e for e in entries if e.get("end") is not None]
    if current_session_start is not None:
        sessions = sessions + [{"start": current_session_start, "end": now, "estimated": False}]

    total = timedelta()
    count = 0
    estimated = False
    for entry in sessions:
        start, end = entry["start"], entry["end"]
        effective_start = max(start, today_start)
        duration = end - effective_start
        if duration <= timedelta(0):
            continue
        total += duration
        count += 1
        if entry.get("estimated"):
            estimated = True
    return TodayUptime(seconds=total.total_seconds(), sessions=count, estimated=estimated)


def format_uptime_today(seconds, session_count, estimated):
    """``"5 h 42 min (2 sessions)"``, prefixed with ``~`` when estimated."""
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    plural = "session" if session_count == 1 else "sessions"
    prefix = "~" if estimated else ""
    return f"{prefix}{hours} h {minutes} min ({session_count} {plural})"


@contextlib.contextmanager
def _locked(path):
    """Hold an exclusive lock on ``path`` for the wrapped block.

    Uses ``fcntl.flock`` with a bounded non-blocking retry, so a stuck
    writer cannot hang a caller past LOCK_BUDGET. On a platform without
    ``fcntl`` (non-POSIX; HostWatch itself only ever runs on Linux), this is
    a no-op best-effort pass-through so the module still works for local
    testing elsewhere.
    """
    try:
        import fcntl
    except ImportError:
        yield
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + LOCK_BUDGET
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out locking {path}") from None
                time.sleep(LOCK_RETRY_INTERVAL)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic_write(path, text, mode="w", encoding="utf-8"):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".hostwatch-", dir=directory)
    try:
        with os.fdopen(fd, mode, encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def prune(entries, retention_days, now):
    """Drop entries older than ``retention_days``; always keep the current session.

    Only the last entry in the list can be "the currently open session" (the
    one record() just appended, or the one still running); an earlier entry
    with no "end" is an orphan left by a session that was never closed (e.g.
    a ledger write failure at shutdown), and ages out like any closed entry
    instead of staying in the ledger forever.
    """
    cutoff = now - timedelta(days=retention_days)
    last_index = len(entries) - 1
    kept = []
    for i, e in enumerate(entries):
        if e["end"] is None:
            if i == last_index or e["start"] >= cutoff:
                kept.append(e)
        elif e["end"] >= cutoff:
            kept.append(e)
    return kept


def _rewrite(path, mutate, retention_days, now):
    """Load, apply ``mutate(entries)``, prune, and atomically save - under lock."""
    try:
        with _locked(_lock_path()):
            entries, status = load_ledger(path)
            if status == "corrupt":
                log.error(f"uptime: ledger {path} is corrupt, rebuilding from this boot")
            entries = mutate(entries)
            entries = prune(entries, retention_days, now)
            serialized = [
                {
                    "start": _format_time(e["start"]),
                    "end": _format_time(e["end"]) if e["end"] is not None else None,
                    "reason": e["reason"],
                    "estimated": e["estimated"],
                }
                for e in entries
            ]
            _atomic_write(path, json.dumps(serialized))
        return True
    except (OSError, TimeoutError) as exc:
        log.error(f"uptime: could not update ledger {path}: {exc}")
        return False


def record_boot(now, retention_days, path=None):
    """Append a new open entry for the boot starting at ``now``."""
    path = path or _ledger_path()

    def mutate(entries):
        return entries + [{"start": now, "end": None, "reason": None, "estimated": False}]

    return _rewrite(path, mutate, retention_days, now)


def close_open_entry(end_time, reason, retention_days, estimated=False, path=None, now=None):
    """Close the most recent open entry, if any.

    ``end_time`` may be None (no last-alive timestamp was ever recorded,
    e.g. a crash before the timer's first tick); the entry is then closed at
    its own start time, a zero-length estimated session, rather than guessed
    from the unrelated time of the current boot. ``now`` is the real current
    time, used for the retention cutoff; it defaults to ``end_time`` only
    when the caller has nothing better (``end_time`` itself may be a stale
    last-alive reading, so pass the real "now" explicitly whenever one is
    available, e.g. from the boot that is doing the closing).
    """
    path = path or _ledger_path()
    now = now or end_time or datetime.now(timezone.utc)

    def mutate(entries):
        for entry in reversed(entries):
            if entry["end"] is None:
                # A last-alive reading from before this session even started
                # (e.g. it crashed before its first tick) is not a usable
                # end time; fall back to the zero-length estimate instead of
                # storing an end before the start.
                usable_end = end_time if end_time is not None and end_time >= entry["start"] else None
                entry["end"] = usable_end if usable_end is not None else entry["start"]
                entry["reason"] = reason
                entry["estimated"] = estimated or usable_end is None
                break
        return entries

    return _rewrite(path, mutate, retention_days, now)


def read_last_alive(path=None):
    path = path or _last_alive_path()
    try:
        with open(path, encoding="ascii") as fh:
            text = fh.read().strip()
        return datetime.fromtimestamp(float(text), timezone.utc)
    except (OSError, ValueError):
        return None


def touch_last_alive(now, path=None):
    """Record ``now`` as the last-alive time, via a small atomic write."""
    path = path or _last_alive_path()
    try:
        _atomic_write(path, f"{now.timestamp():.0f}")
        return True
    except OSError as exc:
        log.error(f"uptime: could not update last-alive timestamp {path}: {exc}")
        return False
