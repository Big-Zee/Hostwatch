"""Loading and validation of /etc/hostwatch/config.ini."""
import configparser
import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_PATH = "/etc/hostwatch/config.ini"
ENV_VAR = "HOSTWATCH_CONFIG"
PLACEHOLDER_WEBHOOK = "https://hooks.slack.com/services/REPLACE/WITH/YOUR-WEBHOOK"

DEFAULT_SKIP_INTERFACES = (
    "docker", "br-", "veth", "virbr", "vnet", "lxc", "lxd",
    "tun", "tap", "cni", "flannel", "zt", "tailscale", "wg",
)
DEFAULT_HEARTBEAT_INTERVAL = 60
HEARTBEAT_INTERVAL_RANGE = (5, 1440)


class ConfigError(Exception):
    """The configuration is missing or invalid. Messages never contain the webhook."""


@dataclass(frozen=True)
class Config:
    webhook_url: str = ""
    skip_interfaces: tuple = DEFAULT_SKIP_INTERFACES
    include_ipv6: bool = False
    timezone: str = "local"
    machine_name: str = ""  # optional friendly label; empty means hostname only
    # Raw [heartbeat] values; validated only by heartbeat_settings(), so a typo
    # there cannot silence boot, login or shutdown messages.
    heartbeat_enabled: str = "true"
    heartbeat_interval: str = str(DEFAULT_HEARTBEAT_INTERVAL)


def resolve_path(explicit=None):
    return explicit or os.environ.get(ENV_VAR) or DEFAULT_PATH


def load(path=None, require_webhook=True):
    """Read and validate the configuration.

    With ``require_webhook=False`` (dry runs) a missing or placeholder webhook
    is accepted; every other setting is still validated.
    """
    path = resolve_path(path)
    parser = _read(path)

    try:
        include_ipv6 = parser.getboolean("boot", "include_ipv6", fallback=False)
    except ValueError as exc:
        raise ConfigError(f"invalid boolean in config {path}: {exc}") from None

    skip = parser.get("boot", "skip_interfaces", fallback=None)
    skip_interfaces = (
        DEFAULT_SKIP_INTERFACES if skip is None
        else tuple(p.strip() for p in skip.split(",") if p.strip())
    )

    cfg = Config(
        webhook_url=parser.get("slack", "webhook_url", fallback="").strip(),
        skip_interfaces=skip_interfaces,
        include_ipv6=include_ipv6,
        timezone=parser.get("display", "timezone", fallback="local").strip() or "local",
        machine_name=parser.get("display", "machine_name", fallback="").strip(),
        heartbeat_enabled=parser.get("heartbeat", "enabled", fallback="true").strip(),
        heartbeat_interval=parser.get("heartbeat", "interval_minutes",
                                      fallback=str(DEFAULT_HEARTBEAT_INTERVAL)).strip(),
    )
    validate(cfg, require_webhook)
    return cfg


def _read(path):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        # utf-8-sig drops the byte-order mark some Windows editors write.
        with open(path, encoding="utf-8-sig") as fh:
            parser.read_file(fh)
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc.strerror or exc}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"config {path} is not valid UTF-8") from None
    except configparser.Error:
        # The parser's message can quote the offending line, which may be the webhook.
        raise ConfigError(f"invalid syntax in config {path}") from None
    return parser


def mask_webhook(url):
    """The webhook as it may be shown: scheme and host, then the last 4 characters.

    Used by install.sh, so the full secret never reaches a terminal or a log.
    """
    url = (url or "").strip()
    if not url or url == PLACEHOLDER_WEBHOOK:
        return "not set"
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        host = None
    if host and parts.scheme and len(url) >= 8:
        return f"{parts.scheme}://{host}/…{url[-4:]}"
    return f"…{url[-4:]}"


# Defaults reported for settings missing from an existing config.
_DEFAULTS = {
    ("slack", "webhook_url"): "none, required",
    ("boot", "skip_interfaces"): ",".join(DEFAULT_SKIP_INTERFACES),
    ("boot", "include_ipv6"): "false",
    ("display", "timezone"): "local",
    ("heartbeat", "enabled"): "true",
    ("heartbeat", "interval_minutes"): str(DEFAULT_HEARTBEAT_INTERVAL),
}


def missing_settings(path, example_path):
    """(section, key, default) for each setting in the example that the config lacks.

    Only uncommented example settings count, so optional ones such as
    machine_name are never reported. The config file itself is not changed.
    """
    have, example = _read(path), _read(example_path)
    return [
        (section, key, _DEFAULTS.get((section, key), example.get(section, key)))
        for section in example.sections()
        for key in example[section]
        if not have.has_option(section, key)
    ]


def heartbeat_settings(cfg):
    """Return (enabled, interval_minutes), or raise ConfigError naming the bad setting."""
    enabled = configparser.ConfigParser.BOOLEAN_STATES.get(cfg.heartbeat_enabled.lower())
    if enabled is None:
        raise ConfigError(f"[heartbeat] enabled must be true or false, got {cfg.heartbeat_enabled!r}")
    low, high = HEARTBEAT_INTERVAL_RANGE
    try:
        interval = int(cfg.heartbeat_interval)
    except ValueError:
        interval = None
    if interval is None or not low <= interval <= high:
        raise ConfigError(f"[heartbeat] interval_minutes must be a whole number from {low} to "
                          f"{high}, got {cfg.heartbeat_interval!r}")
    return enabled, interval


def _well_formed(url):
    """No whitespace or control characters, and a host after the scheme."""
    if any(c.isspace() or not c.isprintable() for c in url):
        return False
    try:
        return bool(urlsplit(url).hostname)
    except ValueError:  # e.g. an unbalanced "[" in the host
        return False


def validate(cfg, require_webhook=True):
    if require_webhook:
        if not cfg.webhook_url or cfg.webhook_url == PLACEHOLDER_WEBHOOK:
            raise ConfigError("webhook not configured: set webhook_url in [slack]")
        if not cfg.webhook_url.startswith("https://"):
            raise ConfigError("webhook_url must be an https:// URL")
        # Never quote the value: it is the secret. An inline "# comment" is the
        # usual cause, since configparser keeps it as part of the value.
        if not _well_formed(cfg.webhook_url):
            raise ConfigError("webhook_url is not a valid URL (it must not contain spaces; "
                              "inline comments are not supported)")
    if cfg.timezone != "local":
        try:
            ZoneInfo(cfg.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"unknown timezone {cfg.timezone!r} in [display]") from None
