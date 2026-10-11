"""Command line: ``hostwatch {boot,shutdown,heartbeat,login,test} [--config PATH] [--dry-run]``."""
import argparse
import json
import os
import signal

from . import config, log, messages, netinfo, processes, sessions, slack, state, timefmt

LOGIN_DEADLINE = 60  # seconds the detached login sender may live

# PAM service -> login type. Anything not listed (su, sudo, cron, systemd-user,
# gdm-launch-environment, ...) is ignored.
LOGIN_SERVICES = {
    "sshd": "SSH",
    "login": "TTY",
    "gdm-password": "Graphical",
    "gdm-autologin": "Graphical",
    "gdm-fingerprint": "Graphical",
    "gdm-smartcard": "Graphical",
    "lightdm": "Graphical",
    "lightdm-autologin": "Graphical",
    "sddm": "Graphical",
    "sddm-autologin": "Graphical",
}


def login_type(pam_type, service):
    """Return the login type for a PAM event, or None when it is not announced."""
    if pam_type != "open_session":
        return None
    return LOGIN_SERVICES.get(service or "")


def _load_config(args, event, default_path=None):
    """Return the config, or None after logging why it cannot be used.

    ``default_path`` replaces the usual lookup ($HOSTWATCH_CONFIG, then the
    default path) when no --config was given. Dry runs fall back to defaults
    so a payload can be previewed anywhere.
    """
    dry_run = getattr(args, "dry_run", False)
    try:
        return config.load(getattr(args, "config", None) or default_path,
                           require_webhook=not dry_run)
    except config.ConfigError as exc:
        if dry_run:
            log.warning(f"{event}: {exc}; dry run uses default settings")
            return config.Config()
        log.error(f"{event}: {exc}")
        return None


def _log_unexpected(event, exc):
    """Log an unexpected error by type and location only.

    The exception text is left out: it can quote the webhook URL.
    """
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    where = (f" at {os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno}"
             if tb is not None else "")
    log.error(f"{event}: unexpected error: {type(exc).__name__}{where}")


def _deliver(args, cfg, payload, delays, event, timeout=slack.TIMEOUT):
    """Send (or, for a dry run, print) the payload. Return True on success."""
    if getattr(args, "dry_run", False):
        body = payload() if callable(payload) else payload
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return True
    return slack.post(cfg.webhook_url, payload, delays, event=event, timeout=timeout)


def run_boot(args):
    dry_run = getattr(args, "dry_run", False)
    # Judge the previous shutdown first, so a broken config cannot leave a stale
    # marker behind that would hide a later crash.
    clean = state.peek_clean() if dry_run else state.consume_clean()
    if not clean:
        log.warning("boot: previous shutdown was not clean")
    try:
        cfg = _load_config(args, "boot")
        if cfg is None:
            return 0
        time_str = timefmt.format_time(timefmt.now(), cfg.timezone)
        boot_time = timefmt.kernel_boot_time()
        boot_str = timefmt.format_time(boot_time, cfg.timezone) if boot_time else None

        def build():
            # Rebuilt on each attempt: addresses may appear only after the first try.
            machine, ips, users = _identity(cfg)
            return messages.boot_message(machine, time_str, boot_str, ips, users,
                                         unclean_previous=not clean)

        _deliver(args, cfg, build, slack.BOOT_DELAYS, "boot")
    except Exception as exc:  # a failed unit would mark boot "degraded"
        _log_unexpected("boot", exc)
    return 0


def _identity(cfg, include_ipv6=None):
    """Machine label, local addresses and logged-in users shown in every message.

    ``include_ipv6`` lets a message type narrow the address rules (the
    heartbeat passes False); None follows the configuration.
    """
    ipv6 = cfg.include_ipv6 if include_ipv6 is None else include_ipv6
    return (
        messages.machine_label(netinfo.hostname(), cfg.machine_name),
        netinfo.local_addresses(cfg.skip_interfaces, ipv6),
        sessions.logged_in_users(),
    )


def run_heartbeat(args):
    """hostwatch-heartbeat.service (started by its timer): one alive message."""
    try:
        cfg = _load_config(args, "heartbeat")
        if cfg is None:
            return 0
        try:
            enabled, _interval = config.heartbeat_settings(cfg)
        except config.ConfigError as exc:
            log.error(f"heartbeat: {exc}")
            return 0
        if not enabled:
            log.info("heartbeat: disabled in config, skipping")
            return 0
        uptime = timefmt.uptime_seconds()
        boot_time = timefmt.kernel_boot_time()
        top = processes.top_processes()  # samples for ~1 s
        machine, ips, users = _identity(cfg, include_ipv6=False)
        payload = messages.heartbeat_message(
            machine,
            timefmt.format_uptime(uptime) if uptime is not None else None,
            timefmt.format_time(boot_time, cfg.timezone, seconds=False) if boot_time else None,
            ips, users, processes.format_table(top),
        )
        _deliver(args, cfg, payload, (), "heartbeat", timeout=slack.HEARTBEAT_TIMEOUT)
    except Exception as exc:  # a bug must not fail the unit; the next tick tries again
        _log_unexpected("heartbeat", exc)
    return 0


def run_heartbeat_interval(args):
    """Admin helper for install.sh: print the validated interval in minutes.

    The webhook is not required: install.sh may run before it is configured.
    """
    try:
        cfg = config.load(getattr(args, "config", None), require_webhook=False)
        print(config.heartbeat_settings(cfg)[1])
    except config.ConfigError as exc:
        log.error(str(exc))
        return 1
    return 0


def run_shutdown(args):
    """ExecStop of hostwatch-shutdown.service: announce a real poweroff/reboot."""
    dry_run = getattr(args, "dry_run", False)
    if not dry_run:
        if not netinfo.system_stopping():
            log.info("shutdown: not a system shutdown, skipping")
            return 0
        # Record first: a slow or killed delivery must not make this look unclean.
        state.mark_clean()
    try:
        cfg = _load_config(args, "shutdown")
        if cfg is None:
            return 0
        event = netinfo.shutdown_kind()
        uptime = timefmt.uptime_seconds()
        machine, ips, users = _identity(cfg)
        payload = messages.shutdown_message(
            machine, event, timefmt.format_time(timefmt.now(), cfg.timezone), ips, users,
            timefmt.format_uptime(uptime) if uptime is not None else None,
        )
        _deliver(args, cfg, payload, (), "shutdown", timeout=slack.SHUTDOWN_TIMEOUT)
    except Exception as exc:  # never let a bug fail the stop job
        _log_unexpected("shutdown", exc)
    return 0


def _detach():
    """Double-fork so pam_exec gets control back at once.

    Returns True in the detached process that should do the work and False in
    the original process, which should return immediately. Without fork
    (non-POSIX) the work runs inline.
    """
    if not hasattr(os, "fork"):
        return True
    pid = os.fork()
    if pid > 0:
        os.waitpid(pid, 0)  # the intermediate child exits straight away
        return False
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    os.chdir("/")
    return True


def run_login(args, environ=None, detach=None, wait=None):
    env = os.environ if environ is None else environ
    wait = wait or sessions.wait_for_session
    kind = login_type(env.get("PAM_TYPE"), env.get("PAM_SERVICE"))
    if kind is None:
        return 0
    user = env.get("PAM_USER") or "unknown"
    tty = env.get("PAM_TTY") or None
    rhost = env.get("PAM_RHOST") or None
    moment = timefmt.now()

    dry_run = getattr(args, "dry_run", False)
    # The real double-fork (not an injected detach, a dry run or a fork-less system).
    detached = not dry_run and detach is None and hasattr(os, "fork")
    if not dry_run and not (detach or _detach)():
        return 0
    if detached:
        # Bound the background sender. No handler: the default action ends the
        # process even inside a hung DNS lookup, where a Python handler never runs.
        signal.alarm(LOGIN_DEADLINE)
    try:
        # As a PAM hook this runs as root with an environment PAM assembled, so
        # $HOSTWATCH_CONFIG is ignored; dry runs and --config still work.
        cfg = _load_config(args, "login", None if dry_run else config.DEFAULT_PATH)
        if cfg is not None:
            if not dry_run:
                # pam_systemd may register this session after our hook started;
                # give logind a moment so the new session shows under Users.
                wait(user, rhost if kind == "SSH" else None)
            time_str = timefmt.format_time(moment, cfg.timezone)

            def build():
                machine, ips, users = _identity(cfg)
                return messages.login_message(machine, user, kind, time_str, ips, users,
                                              tty=tty, rhost=rhost)

            _deliver(args, cfg, build, slack.LOGIN_DELAYS, f"login ({user}, {kind})")
    except Exception as exc:  # never let a bug surface in the login path
        _log_unexpected("login", exc)
    if detached:
        os._exit(0)  # detached child: do not return into the caller
    return 0


def run_test(args):
    cfg = _load_config(args, "test")
    if cfg is None:
        return 1
    machine, ips, users = _identity(cfg)
    payload = messages.test_message(
        machine, timefmt.format_time(timefmt.now(), cfg.timezone), ips, users
    )
    return 0 if _deliver(args, cfg, payload, (), "test") else 1


def build_parser():
    # Options are accepted both before and after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help=f"config file (default: ${config.ENV_VAR} or {config.DEFAULT_PATH})")
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                        help="print the Slack payload instead of sending it")

    parser = argparse.ArgumentParser(
        prog="hostwatch", parents=[common],
        description="Slack notifications for host boot, shutdown, heartbeat and user logins.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("boot", parents=[common], help="send the boot notification (systemd unit)")
    sub.add_parser("shutdown", parents=[common],
                   help="send the shutdown notification (ExecStop of the shutdown unit)")
    sub.add_parser("heartbeat", parents=[common],
                   help="send a heartbeat with uptime, users and top processes (timer)")
    sub.add_parser("login", parents=[common], help="send a login notification (pam_exec hook)")
    sub.add_parser("test", parents=[common], help="send a test message; exit 1 if it fails")
    sub.add_parser("heartbeat-interval", parents=[common])  # hidden: used by install.sh
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {"boot": run_boot, "shutdown": run_shutdown, "heartbeat": run_heartbeat,
                "heartbeat-interval": run_heartbeat_interval, "login": run_login,
                "test": run_test}
    return handlers[args.command](args)
