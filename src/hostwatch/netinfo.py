"""Host identity and network addresses."""
import ipaddress
import json
import socket
import subprocess

from . import log


def hostname():
    return socket.gethostname()


def _is_loopback(address):
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def parse_ip_json(data, skip_prefixes, include_ipv6=False):
    """Pick addresses from ``ip -j addr show`` output.

    Keeps interfaces that are up, drops loopback interfaces and addresses
    (127.0.0.0/8, ::1) and names starting with any of ``skip_prefixes``.
    IPv4 always; IPv6 only with ``include_ipv6`` and global scope.
    Returns a list of (interface, address).
    """
    result = []
    for iface in data:
        name = iface.get("ifname", "")
        flags = iface.get("flags", [])
        if name == "lo" or "LOOPBACK" in flags:
            continue
        if any(name.startswith(prefix) for prefix in skip_prefixes):
            continue
        state = iface.get("operstate", "")
        if not (state == "UP" or (state == "UNKNOWN" and "UP" in flags)):
            continue
        for addr in iface.get("addr_info", []):
            local = addr.get("local")
            if not local or _is_loopback(local):
                continue
            if addr.get("family") == "inet":
                result.append((name, local))
            elif addr.get("family") == "inet6" and include_ipv6 and addr.get("scope") == "global":
                result.append((name, local))
    return result


REBOOT_TARGETS = ("reboot.target", "kexec.target", "soft-reboot.target")
SYSTEMCTL_TIMEOUT = 2


def _systemctl(args, run):
    """Return systemctl's stdout, or None if it cannot be run in time."""
    try:
        proc = run(["systemctl", *args], capture_output=True, text=True, errors="replace",
                   timeout=SYSTEMCTL_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout


def system_stopping(run=subprocess.run):
    """True only while the whole system is shutting down (not on a unit stop/restart)."""
    out = _systemctl(["is-system-running"], run)
    return out is not None and out.strip() == "stopping"


def shutdown_kind(run=subprocess.run):
    """Return "Rebooting" or "Shutting down" from the pending systemd shutdown job."""
    out = _systemctl(["list-jobs", "--no-legend", "--plain"], run) or ""
    units = {fields[1] for fields in (line.split() for line in out.splitlines()) if len(fields) > 1}
    return "Rebooting" if units.intersection(REBOOT_TARGETS) else "Shutting down"


def local_addresses(skip_prefixes, include_ipv6=False, run=subprocess.run):
    try:
        proc = run(["ip", "-j", "addr", "show"], capture_output=True, text=True, errors="replace",
                   timeout=5, check=True)
        data = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.warning(f"could not list local addresses: {type(exc).__name__}: {exc}")
        return []
    return parse_ip_json(data, skip_prefixes, include_ipv6)

