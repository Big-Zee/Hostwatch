"""Clean-shutdown marker in /var/lib/hostwatch.

A clean shutdown writes the marker; the next boot consumes it. A boot that
finds no marker follows a power loss, crash or hard reset.
"""
import os

from . import log

DEFAULT_STATE_DIR = "/var/lib/hostwatch"
STATE_DIR_ENV = "HOSTWATCH_STATE_DIR"
MARKER = "clean_shutdown"


def _marker_path():
    return os.path.join(os.environ.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR, MARKER)


def mark_clean():
    """Record a clean shutdown, durably (it must survive the poweroff that follows)."""
    path = _marker_path()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(os.path.dirname(path))
        return True
    except OSError as exc:
        log.error(f"shutdown: could not record clean shutdown in {path}: {exc.strerror or exc}")
        return False


def _fsync_dir(directory):
    if not hasattr(os, "O_DIRECTORY"):
        return  # not available on non-POSIX systems
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def peek_clean():
    """Return whether the previous shutdown was recorded as clean, without consuming it."""
    return os.path.exists(_marker_path())


def consume_clean():
    """Return whether the previous shutdown was recorded as clean, and remove the record."""
    path = _marker_path()
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        log.error(f"boot: could not remove clean-shutdown marker {path}: {exc.strerror or exc}")
        # It exists but cannot be removed; still report what it says.
        return True
