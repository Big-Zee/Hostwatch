# Tasks

## 1. Project scaffolding

- [x] 1.1 Create `src/slack_heartbeat/__init__.py`, `bin/slack-heartbeat` (`#!/usr/bin/python3 -I` wrapper that adds `/usr/local/lib/slack-heartbeat`, or the repo's `src/` when run from a checkout, to `sys.path` and calls `cli.main()`), and an empty `tests/` package. Verify that `python3 bin/slack-heartbeat --help` runs from the repo.

## 2. Configuration (`heartbeat-config`)

- [x] 2.1 Add `config.example.ini` with sections `[slack]`, `[boot]` and `[display]`, a placeholder webhook and documented defaults. Verify with `git grep hooks.slack.com` that only the placeholder appears.
- [x] 2.2 Implement `config.py`: default path, `--config` / `SLACK_HEARTBEAT_CONFIG` override, defaults, and validation that rejects a missing, placeholder or non-https webhook and an unknown timezone. Verify `tests/test_config.py` covers defaults, override path, placeholder, bad URL and bad timezone.

## 3. Slack delivery (`slack-delivery`)

- [x] 3.1 Implement `slack.py` `post()` with a request timeout, retry/backoff on network errors, 429 and 5xx, no retry on other 4xx, and syslog logging that never includes the webhook. Verify `tests/test_slack.py`, with `urlopen` and `sleep` mocked, covers success, a transient failure followed by success, 404 with no retry, exhausted retries, and that log text excludes the URL.
- [x] 3.2 Implement `timefmt.py`: display-timezone formatting `YYYY-MM-DD HH:MM:SS TZ` and kernel boot time from `/proc/stat`. Verify `tests/test_timefmt.py` checks the format for `Europe/Warsaw` (CEST and CET dates) and `local`, and parses a fixture `btime`.
- [x] 3.3 Implement `messages.py` as pure Block Kit builders (header, field section, context footer, `text` fallback) for the test message. Verify a unit test asserts the block structure and the fallback text.
- [x] 3.4 Implement `cli.py` with argparse, the `test` subcommand, the global `--dry-run` (prints payload JSON, sends nothing) and `--config`. Exit status is 0 after logged errors. Verify that `python3 bin/slack-heartbeat test --dry-run --config config.example.ini` prints JSON and makes no network call, and that a placeholder config without `--dry-run` logs "webhook not configured".

## 4. Boot notification (`boot-notification`)

- [x] 4.1 Implement `netinfo.py`: hostname, local IPs from `ip -j addr` with UP filter, loopback and skip-prefix exclusion and optional IPv6, plus public IP lookup with a 5 s timeout and IP validation that returns `None` on failure. Verify `tests/test_netinfo.py` uses fixture JSON (lo, enp3s0, wlp2s0, docker0, veth*, virbr0, tailscale0) to check filtering and IPv6 toggling, and checks the public IP for success, timeout and garbage-body cases.
- [x] 4.2 Add the boot message builder and the `boot` subcommand: time, kernel boot time, hostname, local IPs (or "none found"), public IP (value, "unavailable" or "disabled"), and the boot retry schedule (5, 10, 20, 40, 60 s). Verify unit tests cover each public IP state and the empty-IP case, and that `boot --dry-run` prints the expected payload.
- [ ] 4.3 Add `systemd/slack-heartbeat-boot.service` (`Type=simple`, `Wants`/`After=network-online.target`, `WantedBy=multi-user.target`, `TimeoutStopSec=5`). Verify `systemd-analyze verify systemd/slack-heartbeat-boot.service` reports no errors on an Ubuntu host.

## 5. Login notification (`login-notification`)

- [x] 5.1 Add the login message builder and the `login` subcommand. It reads `PAM_TYPE`, `PAM_SERVICE`, `PAM_USER`, `PAM_TTY` and `PAM_RHOST`, acts only on `open_session`, and maps allow-listed services to Graphical, TTY or SSH (ignoring all others). It then double-forks with `setsid` and closed stdio, returns 0 at once, and sends from the child with the login retry schedule (2, 5 s). Verify unit tests cover the service mapping, ignored services (`su`, `sudo`, `systemd-user`, `cron`, `gdm-launch-environment`), `close_session` being ignored, SSH content including the remote IP, and TTY content including the terminal, and that `PAM_TYPE=open_session PAM_SERVICE=sshd PAM_USER=alice PAM_RHOST=203.0.113.7 bin/slack-heartbeat login --dry-run` prints the payload.
- [ ] 5.2 Add the `pam/slack-heartbeat` pam-auth-update profile (Name, Default: yes, Priority, Session-Type: Additional, `Session: optional pam_exec.so quiet /usr/local/bin/slack-heartbeat login`). Verify that after install `grep slack-heartbeat /etc/pam.d/common-session` shows the `optional` line.

## 6. Install / uninstall (`service-installation`)

- [ ] 6.1 Write `install.sh` (`set -euo pipefail`, root check). It copies the package, wrapper, unit and PAM profile. It creates the config from the example with mode `600 root:root` only if absent, takes the webhook from `SLACK_WEBHOOK_URL` or a hidden prompt and never echoes it, then runs `daemon-reload`, `enable` (without `--now`) and `pam-auth-update --package --enable`. Verify that `shellcheck install.sh` is clean and that running it twice on a test VM leaves an existing config untouched.
- [ ] 6.2 Write `uninstall.sh` (root check). It removes the PAM profile via `pam-auth-update --package --remove` first, then disables and removes the unit and deletes the files. `--purge` also removes `/etc/slack-heartbeat`. It must be idempotent. Verify that `shellcheck uninstall.sh` is clean and that after running it `/etc/pam.d/common-session` has no slack-heartbeat line and `systemctl status slack-heartbeat-boot` reports not found.
- [x] 6.3 Update `README.md` with purpose, install (including `SLACK_WEBHOOK_URL`), config reference, the reasoning for PAM over a user unit, test and dry-run commands, troubleshooting (`journalctl -u slack-heartbeat-boot`, `journalctl -t slack-heartbeat`) and uninstall. Verify that each documented command matches the implemented CLI flags.

## 7. Acceptance on Ubuntu 24.04

- [ ] 7.1 On a fresh Ubuntu 24.04 VM, run `sudo SLACK_WEBHOOK_URL=... ./install.sh`, then `slack-heartbeat test`, then reboot. Verify exactly one test message and then exactly one boot message with correct time/TZ, hostname, non-virtual local IPs and public IP, and `ls -l /etc/slack-heartbeat/config.ini` shows `-rw------- root root`.
- [ ] 7.2 Log in once on the desktop, once over SSH from another host, and once on a TTY (Ctrl+Alt+F3), then run `sudo -i` and log out. Verify exactly one Graphical, one SSH (with remote IP) and one TTY message, and nothing for sudo or logout.
- [ ] 7.3 Disconnect the network and reboot. Verify that boot time is unchanged (`systemd-analyze`), `systemctl --failed` is empty, and `journalctl -t slack-heartbeat` shows the retries and the final failure. Also set the public IP URL to an unreachable host and verify the boot message still arrives with "unavailable".
- [ ] 7.4 Run `sudo ./uninstall.sh`, reboot and log in. Verify that no messages are sent and `/etc/slack-heartbeat` still exists. Run `sudo ./uninstall.sh --purge` and verify it is removed.

## Workflow follow-up

- Archive the change with `/opsx:archive` after acceptance passes.
