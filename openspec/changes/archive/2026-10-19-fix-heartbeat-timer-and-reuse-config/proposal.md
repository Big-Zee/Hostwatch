# Proposal

## Why

On a real Ubuntu host (Maja-GAMING-X-V2) the heartbeat never started after a reboot. `hostwatch-heartbeat.timer` sat in "active (elapsed)" with no next run, and only a manual `systemctl start hostwatch-heartbeat.service` got the schedule going. The cause is in the timer drop-in that `install.sh` writes:

```
OnBootSec=
OnBootSec=60min
OnUnitActiveSec=
OnUnitActiveSec=60min
```

systemd.timer(5) says that assigning an empty string to *any* timer option resets the whole list of timers. The `OnUnitActiveSec=` line therefore also drops the `OnBootSec=60min` set just above it. The only timer left is `OnUnitActiveSec`, which has no reference point after boot because the service has not run yet. That matches what was observed: `TimersMonotonic` lists only `OnUnitActiveUSec=1h`. The heartbeat requirement ("the first heartbeat comes one interval after boot") is not met on any installed host.

Separately, re-running `install.sh` after an upgrade gives no sign that it is reusing the existing configuration, and there is no supported way to replace the webhook. Today the only options are hand-editing a root-only file or uninstalling with `--purge`. Administrators upgrading several machines want to see which configuration is being kept, confirm it in one keystroke, and change the webhook safely when needed.

## What Changes

- **Heartbeat timer:** The drop-in sets the schedule with a single reset line, then `OnActiveSec=<interval>` (counted from when the timer starts, which is early in boot) and `OnUnitActiveSec=<interval>`. It no longer relies on `OnBootSec`. The base timer unit uses the same pair.
- **Heartbeat check after install:** `install.sh` checks with `systemctl show -p TimersMonotonic` and `systemctl list-timers` that the timer has a monotonic entry and a next run. If not, it prints a warning.
- **Heartbeat after install or interval change:** Restarting the timer no longer fires a heartbeat at once on a long-running host. The next heartbeat comes one interval after the install. This replaces the behaviour documented for Finding #15.
- **Existing configuration reused with one confirmation:** When `/etc/hostwatch/config.ini` exists, `install.sh` does not ask for the webhook. It shows the current settings, with the webhook masked to scheme, host and last 4 characters, and asks `Use this configuration? [Y/n]`.
  - **Y or Enter** keeps the file byte-for-byte unchanged.
  - **n** asks for a new webhook (hidden input). It must start with `https://hooks.slack.com/`. The old file is backed up to `config.ini.bak` (root, `600`) before the new webhook is written.
- **Installer flags:**
  - `--yes` keeps the existing config without asking.
  - `--reconfigure` always asks for a new webhook.
  - A run without a terminal keeps the existing config without asking.
  - `SLACK_WEBHOOK_URL` replaces an existing webhook only with `--reconfigure`.
- **Fresh install:** As today, the config is created from `config.example.ini` and the installer asks for the webhook. It now also asks for an optional `machine_name`. A webhook entered at install must start with `https://hooks.slack.com/`.
- **Missing settings:** The installer lists settings that a newer version supports but the existing file lacks, with the default each will use. It never adds them to the file.
- **The full webhook URL is never printed** by the installer, to the terminal or the journal.
- **Documentation:** README updates for the confirmation prompt, `--yes`, `--reconfigure`, `config.ini.bak` and the new heartbeat timing. The repository has no separate INSTALL file, so the README's Install section serves as the install notes.

Not changed: message content, boot, login and shutdown behaviour, the heartbeat message format, and the runtime check of the webhook in `config.py`, which still accepts any `https://` URL. No legacy `/etc/slack-heartbeat/` configuration is read: slack-heartbeat was never installed on any host (security review, Finding #17).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `heartbeat-notification`: the first heartbeat after boot must actually arrive without manual action, and after an install or interval change the next heartbeat comes one interval later instead of at once.
- `service-installation`: reuse of an existing config with a masked summary and one confirmation, `--yes` / `--reconfigure`, non-interactive behaviour, `config.ini.bak` before any change, a `machine_name` prompt on fresh install, stricter webhook check at install, reporting of missing settings, and a check after install that the heartbeat timer is scheduled.

## Impact

- `systemd/hostwatch-heartbeat.timer`: `OnBootSec` is replaced by `OnActiveSec`.
- `install.sh`:
  - argument parsing
  - the existing-config summary and prompt
  - backup before writing
  - `machine_name` prompt
  - the new drop-in content
  - the post-install timer check
- `src/hostwatch/cli.py` and `src/hostwatch/config.py`: a hidden admin subcommand that prints the masked config summary and the missing settings for `install.sh`. Config parsing stays in Python, and the webhook is masked before it leaves the process.
- `tests/`: unit tests for the masking and summary helper. Installer and timer behaviour are checked on an Ubuntu 24.04 VM.
- `README.md`: the Install, Configuration and Heartbeat sections.
- Hosts that are already installed pick up the fixed drop-in the next time `install.sh` is run. Until then they keep the broken schedule.
