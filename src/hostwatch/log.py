"""Logging to the systemd journal via syslog (ident ``hostwatch``).

Messages are also echoed to stderr when it is a terminal, so an administrator
running a command by hand sees them. On systems without the ``syslog`` module
(non-POSIX development machines) messages go to stderr only.
"""
import sys

try:
    import syslog
except ImportError:  # pragma: no cover - not available on Windows
    syslog = None

IDENT = "hostwatch"
_opened = False


def _emit(level, message):
    global _opened
    if syslog is not None:
        if not _opened:
            syslog.openlog(IDENT, syslog.LOG_PID, syslog.LOG_DAEMON)
            _opened = True
        priority = {"info": syslog.LOG_INFO, "warning": syslog.LOG_WARNING}.get(
            level, syslog.LOG_ERR
        )
        syslog.syslog(priority, message)
    try:
        if syslog is None or sys.stderr.isatty():
            sys.stderr.write(f"{IDENT}: {level}: {message}\n")
    except (AttributeError, OSError, ValueError):
        pass  # stderr closed (detached login hook)


def info(message):
    _emit("info", message)


def warning(message):
    _emit("warning", message)


def error(message):
    _emit("error", message)
