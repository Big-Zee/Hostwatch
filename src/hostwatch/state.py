"""Clean-shutdown marker and login-cooldown markers in /var/lib/hostwatch.

A clean shutdown writes the marker; the next boot consumes it. A boot that
finds no marker follows a power loss, crash or hard reset.
"""
import hashlib
import os
import time

from . import log

DEFAULT_STATE_DIR = "/var/lib/hostwatch"
STATE_DIR_ENV = "HOSTWATCH_STATE_DIR"
MARKER = "clean_shutdown"
LOGIN_COOLDOWN_DIR = "login-cooldown"


def _state_dir():
    return os.environ.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR


def _marker_path():
    return os.path.join(_state_dir(), MARKER)


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


def login_recently_notified(key, window_seconds):
    """Whether a login notification for ``key`` went out within ``window_seconds``.

    ``key`` (e.g. a user/login-type/remote-host triple) is hashed into a
    filename, so it never has to be filesystem-safe. The marker's mtime is
    always bumped to now, so a steady burst keeps renewing the cooldown and
    only the first notification in it is sent; this is best-effort (no
    locking against concurrent logins) since missing a rare race just sends
    one extra notification.
    """
    if window_seconds <= 0:
        return False
    now = time.time()
    directory = os.path.join(_state_dir(), LOGIN_COOLDOWN_DIR)
    path = os.path.join(directory, hashlib.sha256(key.encode()).hexdigest())
    try:
        recent = (now - os.stat(path).st_mtime) < window_seconds
    except OSError:
        recent = False
    try:
        os.makedirs(directory, exist_ok=True)
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
        os.utime(path, (now, now))
    except OSError as exc:
        log.error(f"login: could not record cooldown marker {path}: {exc.strerror or exc}")
    return recent
