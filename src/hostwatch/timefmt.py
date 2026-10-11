"""Timestamp formatting in the configured display timezone."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FORMAT = "%Y-%m-%d %H:%M:%S %Z"
FORMAT_MINUTES = "%Y-%m-%d %H:%M %Z"


def now():
    return datetime.now(timezone.utc)


def format_time(moment, tz_name="local", seconds=True):
    """Format an aware datetime as ``YYYY-MM-DD HH:MM:SS TZ`` (or without seconds)."""
    if tz_name == "local":
        local = moment.astimezone()
    else:
        local = moment.astimezone(ZoneInfo(tz_name))
    return local.strftime(FORMAT if seconds else FORMAT_MINUTES)


def uptime_seconds(uptime_path="/proc/uptime"):
    """Return system uptime in seconds from /proc/uptime, or None."""
    try:
        with open(uptime_path, encoding="ascii") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def format_uptime(seconds):
    """Format seconds as ``up [D d ]H h M min``, dropping leading zero units."""
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if days or hours:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return "up " + " ".join(parts)


def kernel_boot_time(stat_path="/proc/stat"):
    """Return the kernel boot time from ``btime`` in /proc/stat, or None."""
    try:
        with open(stat_path, encoding="ascii") as fh:
            for line in fh:
                if line.startswith("btime "):
                    return datetime.fromtimestamp(int(line.split()[1]), timezone.utc)
    except (OSError, ValueError, IndexError):
        pass
    return None
