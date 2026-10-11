# Design

## Context

The repo starts empty apart from a README, a LICENSE and the Python template `.gitignore`. That template ignores `lib/`, `build/`, `config.ini` and `.env`. The target is stock Ubuntu 24.04: Python 3.12, systemd, iproute2 (`ip -j`), PAM with `pam-auth-update`, and GDM on the desktop. For motivation see proposal.md (Why); for behavior see `specs/`.

## Goals / Non-Goals

**Goals:**
- A single program with subcommands. It can grow later events (uptime, top processes, shutdown) without restructuring.
- Nothing on the boot or login path can block, delay or fail.
- Clean, reversible host changes that use the distribution's own mechanisms (systemd units, `pam-auth-update`), never hand-edited system files.

**Non-Goals:**
- Packaging as `.deb`, running in a virtualenv, or supporting distros other than Ubuntu 24.04. Other systemd and PAM distros will likely work but are not verified.
- Message deduplication across reboots, rate limiting, or a persistent queue for messages that failed.
- Hourly reports and shutdown notification (later changes).

## Decisions

### D1. Login detection: PAM `pam_exec` rather than a systemd user unit
The hook is a `pam-auth-update` profile (`/usr/share/pam-configs/slack-heartbeat`, Session-Type: Additional). It adds `session optional pam_exec.so quiet /usr/local/bin/slack-heartbeat login` to `common-session`, which sshd, login, gdm-password, gdm-autologin and lightdm all include.

Why PAM:
- **Per session.** It fires on every `open_session`. A systemd user unit runs once per *user manager*, so an SSH login while the desktop session is open would not be announced, which breaks the spec.
- **Context.** PAM passes `PAM_USER`, `PAM_SERVICE`, `PAM_TTY`, `PAM_RHOST` and `PAM_TYPE`. A user unit has no clean way to get the remote IP or the login type.
- **System-wide and root.** No per-user enabling is needed, and it can read the root-only config.
- **Reversible.** `pam-auth-update --enable/--remove` regenerates `common-session` safely.

Alternatives considered:
- systemd user unit: misses repeat sessions and the remote IP (see above).
- `/etc/profile.d` script: misses graphical sessions and runs as the user.
- sshd `ForceCommand`/`sshrc`: SSH only.
- Polling `loginctl`/journald watcher: adds a long-running daemon for little gain.

Safety measures:
- The PAM control is `optional`, so a missing or crashing hook cannot deny a login.
- The hook detaches with a double fork plus `setsid`, closes stdio, and returns 0 at once. Delivery happens in the detached child.
- Filtering: the hook only acts when `PAM_TYPE=open_session` and `PAM_SERVICE` is in an allow-list mapped to a login type:
  - `sshd` → SSH
  - `login` → TTY
  - `gdm-password`, `gdm-autologin`, `gdm-fingerprint`, `gdm-smartcard`, `lightdm`, `sddm` → Graphical

  Everything else is ignored: `systemd-user` (which also includes `common-session` and would cause duplicates), `su`, `sudo`, `cron`, `gdm-launch-environment` and others. An allow-list beats a deny-list, because unknown services stay silent rather than noisy.

### D2. Boot: `Type=simple` service after `network-online.target`
`slack-heartbeat-boot.service` has these settings:
- `Wants=network-online.target`, `After=network-online.target`, `WantedBy=multi-user.target`
- `Type=simple`, `ExecStart=/usr/local/bin/slack-heartbeat boot`
- `TimeoutStopSec=5`
- `SuccessExitStatus` default. The program always exits 0 after handling errors itself.

A target gets an implicit `After=` on the units it wants. With `Type=oneshot`, `multi-user.target` (and the graphical login) would therefore wait for all retries. With `Type=simple` the unit counts as started as soon as the process starts, so boot never waits.

`network-online.target` is necessary but not enough: on desktops NetworkManager-wait-online may report online before DNS works. The in-process retry/backoff (D4) covers that gap.

Alternative: a systemd timer with `OnBootSec=`. It adds a unit for no benefit.

### D3. Code layout
- `src/slack_heartbeat/` is a package with small modules:
  - `config` – INI loading, defaults, validation
  - `netinfo` – hostname, local IPs, public IP
  - `timefmt` – timestamp formatting, kernel boot time
  - `slack` – posting, retry
  - `messages` – pure payload builders
  - `cli` – argparse subcommands `boot`, `login`, `test`, plus `--dry-run` and `--config`
- `bin/slack-heartbeat` is a tiny wrapper with shebang `#!/usr/bin/python3 -I`. Isolated mode ignores user site-packages and `PYTHON*` env vars, which matters because it runs as root from PAM. It adds `/usr/local/lib/slack-heartbeat` to `sys.path`.
- The code lives in `src/`, not `lib/`, because the `.gitignore` template ignores `lib/`.
- `messages` is pure (data in, dict out), so tests need no network or system state. Later events add a builder and a subcommand.

### D4. Delivery and retry
`urllib.request` posts JSON with a 10 s timeout. Retries cover `URLError`/timeouts, 429 and 5xx; other 4xx errors fail at once. Schedules:
- **boot**: 6 attempts, waiting 5, 10, 20, 40, 60 s between them (about 2.5 min in total).
- **login**: 3 attempts, waiting 2 and 5 s. The network is normally already up at login.

Because the boot unit is `simple`, retry time never affects boot.

### D5. Logging
The stdlib `syslog` module is used with ident `slack-heartbeat` and facility `LOG_DAEMON`. Messages land in the journal, filterable with `journalctl -t slack-heartbeat`. This works the same from systemd and from the detached PAM child, which has no stdout. The webhook URL is never formatted into log text; errors log the HTTP status or exception class plus message.

### D6. Network information
- **Local IPs**: parse `ip -j addr show`. Keep only interfaces with `operstate == UP`, or `UNKNOWN` with an address. Drop `lo` and names starting with a configured skip prefix. Keep `inet`; keep `inet6` only when `include_ipv6 = true`, and then only scope `global`.
  - Shown as `enp3s0: 192.168.1.20`.
  - Alternative: `socket`/`fcntl` ioctls give only one IPv4 per interface and no operstate.
- **Public IP**: GET `public_ip_url` with a 5 s timeout, one attempt. The response body is stripped and validated with `ipaddress.ip_address`. On any error the value is `None`, shown as "unavailable".

### D7. Time
`zoneinfo` (stdlib) is used for the display timezone. `local` means `datetime.now().astimezone()`. The format is `%Y-%m-%d %H:%M:%S %Z`. Kernel boot time comes from `btime` in `/proc/stat`.

### D8. Message layout (Block Kit)
- **header**: ":large_green_circle: my-pc is up" for boot, ":bust_in_silhouette: alice logged in to my-pc" for login.
- **section**: two-column `fields` in mrkdwn (`*Time*\n2026-10-11 12:01:33 CEST`, and so on). Fields stack into one column on mobile.
- **context**: a footer reading `slack-heartbeat`.
- Top-level `text` is the one-line fallback used for push previews.

### D9. Install / uninstall
**install.sh** (bash, `set -euo pipefail`, checks for root) does the following:
1. Install the package to `/usr/local/lib/slack-heartbeat/slack_heartbeat/` (mode 644) and the wrapper to `/usr/local/bin/slack-heartbeat` (mode 755).
2. Install the unit to `/etc/systemd/system/`.
3. Install the PAM profile to `/usr/share/pam-configs/slack-heartbeat`.
4. If `/etc/slack-heartbeat/config.ini` does not exist, install it from the example with `install -m 600 -o root -g root`. Then substitute the webhook from `SLACK_WEBHOOK_URL`, or from a `read -s` prompt when stdin is a TTY. The webhook is never echoed.
5. Run `systemctl daemon-reload`, `systemctl enable slack-heartbeat-boot.service` (with no `--now`, which would send a boot message at install time), and `pam-auth-update --package --enable slack-heartbeat`.

**uninstall.sh** reverses this:
1. `pam-auth-update --package --remove slack-heartbeat`, then delete the profile.
2. `systemctl disable`, then delete the unit and run `daemon-reload`.
3. Delete the library and the wrapper.
4. With `--purge`, also delete `/etc/slack-heartbeat`.

Both scripts are idempotent. The PAM profile is removed from the PAM stack *before* the binary is deleted. (`optional` protects logins even if this order were reversed.)

## Risks / Trade-offs

- [`common-session` is also included by services not on the allow-list] → Allow-list filtering in the hook. The cost is one short Python start-up per such session, and the hook exits at once.
- [Python start-up adds latency to every login, about 30–50 ms] → The hook forks and returns right after reading the PAM env. This is acceptable. If it ever matters, a tiny shell shim could filter before starting Python.
- [Display managers other than GDM/LightDM/SDDM use different PAM service names] → Unknown services stay silent. The allow-list is easy to extend later, and the README documents it.
- [`network-online.target` reached before DNS or the internet works] → Boot retry schedule (D4).
- [GDM autologin or fast-user-switch may open extra PAM sessions] → Only allow-listed login services count. The greeter (`gdm-launch-environment`) is excluded. To be verified during acceptance testing.
- [The public IP service is a third party that sees the host's IP] → The lookup is configurable and can be disabled, and it runs only at boot.
- [Webhook leakage via `ps` or logs] → The webhook is never passed on a command line or logged. The config is mode 600 and the install prompt does not echo.
- [A failed boot message is lost (no queue)] → Accepted for this change. The journal records it. A later change could add a "missed boot" catch-up.

## Migration Plan

This is a greenfield change with nothing to migrate.

- **Rollout**: `sudo ./install.sh`, then `slack-heartbeat test`, then reboot.
- **Rollback**: `sudo ./uninstall.sh` (add `--purge` to drop the config).
