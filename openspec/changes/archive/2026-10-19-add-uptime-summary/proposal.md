# Proposal

## Why

Shutdown/reboot and heartbeat messages only show the current session's uptime. An admin watching the Slack channel cannot tell how much of today the machine was actually on without manually summing boot/shutdown times across reboots and crashes. A small on-disk ledger of boot sessions lets every message type report "uptime today" cheaply and reliably, including an honest estimate after a crash.

## What Changes

- Add a root-owned boot-session ledger in `/var/lib/hostwatch/` (e.g. `uptime.json`): one entry per boot with boot time, end time and end reason (clean shutdown, reboot, unclean/estimated). Written atomically (temp file + rename) with a lock file guarding concurrent writers.
- Write the boot entry at `hostwatch boot`; close the entry at `hostwatch shutdown` with the real end time and reason.
- Add a lightweight root timer (`hostwatch-last-alive.timer`/`.service`, default every 5 minutes, configurable) that atomically updates a small "last alive" timestamp file; `hostwatch heartbeat` also refreshes it. At boot, an entry left open by the previous run is closed using that timestamp and marked estimated.
- Add one shared pure function (in a new `uptime.py` module) that computes "uptime today" (local calendar day, summed across sessions overlapping today, sessions clipped to 00:00, estimated sessions marked with a leading `~`) from the ledger plus the current running session. Used by all three message builders.
- Shutdown/reboot message: keep the existing session-uptime field and add an "Uptime today" field that includes the session now ending.
- Heartbeat message: add an "Uptime today" field next to the existing "Uptime" field, including the running session up to now.
- Boot message: optionally add "Uptime today before this boot" (today's total excluding the session about to start); the existing unclean-shutdown warning logic is unchanged.
- Ledger reads/writes degrade gracefully: missing, empty or corrupt ledger is logged and treated as starting fresh from the current boot; the daily-summary field is simply omitted from a message (never fails or delays boot/login/shutdown) if anything about the ledger goes wrong.
- Prune ledger entries older than a configurable retention period (default 90 days), on boot.
- New `[uptime]` section in `config.ini`: `daily_summary_enabled` (default true), `last_alive_interval_minutes` (default 5), `retention_days` (default 90).
- `install.sh` creates `/var/lib/hostwatch` with the existing permissions flow (already does), installs/enables the new last-alive timer, and verifies it has a next run the same way it already verifies the heartbeat timer. `uninstall.sh` removes the new timer and, like the ledger directory already removed today, asks before deleting the ledger specifically mentioned to the admin.
- New capability spec `uptime-summary` describing the ledger, the shared calculation, and its reliability guarantees. `shutdown-notification`, `heartbeat-notification`, `boot-notification`, `hostwatch-config` and `service-installation` get delta requirements for the new fields, config keys and installer/uninstaller behavior.

Out of scope: logoff notifications, weekly/monthly reports, per-user usage stats, CSV export, graphs, and suspend/hibernate-aware accounting (documented as a limitation; time is wall clock from boot to shutdown).

## Capabilities

### New Capabilities
- `uptime-summary`: the boot-session ledger, the last-alive timer, the shared "uptime today" calculation (including estimation after an unclean shutdown and calendar-day clipping), ledger reliability (atomic writes, locking, corruption/missing-ledger recovery, pruning) and its config keys.

### Modified Capabilities
- `shutdown-notification`: shutdown/reboot message adds an "Uptime today" field alongside the existing session uptime.
- `heartbeat-notification`: heartbeat message adds an "Uptime today" field alongside the existing session uptime.
- `boot-notification`: boot message may add an optional "Uptime today before this boot" field; existing content and unclean-shutdown warning behavior stay as specified.
- `hostwatch-config`: adds the `[uptime]` settings (`daily_summary_enabled`, `last_alive_interval_minutes`, `retention_days`) with defaults and validation.
- `service-installation`: install script additionally installs/enables the last-alive timer and verifies it has a next run; uninstall script additionally removes that timer and, after asking, the ledger.

## Impact

- New module `src/hostwatch/uptime.py` (ledger I/O, shared "uptime today" calculation) and its unit tests.
- `src/hostwatch/cli.py`: `run_boot` writes a ledger entry and prunes old entries; `run_shutdown` closes the entry; new `run_last_alive` handler for the timer; `run_heartbeat` also refreshes the last-alive timestamp and computes "uptime today".
- `src/hostwatch/messages.py`: `boot_message`, `shutdown_message`, `heartbeat_message` gain the new field(s).
- `src/hostwatch/config.py`: new `[uptime]` settings and a `uptime_settings()` validator.
- `src/hostwatch/state.py` or `uptime.py`: lock file / atomic write helpers reused from existing clean-shutdown marker patterns.
- New `systemd/hostwatch-last-alive.service` and `.timer`.
- `install.sh`, `uninstall.sh`, `config.example.ini`.
- `openspec/specs/uptime-summary/spec.md` (new), plus delta specs for `shutdown-notification`, `heartbeat-notification`, `boot-notification`, `hostwatch-config`, `service-installation`.
- `README.md` and install notes (suspend/hibernate limitation, new config keys, new timer).
