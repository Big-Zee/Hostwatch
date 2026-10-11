# Proposal

## Why

Boot, shutdown and login messages show *events*. Nothing shows that a PC is still running in between, who is using it, or what is keeping it busy. A regular heartbeat answers "is it alive, who is on it, and what is it doing" for every machine posting to the shared channel.

## What Changes

- **New heartbeat message** sent at a fixed interval while the PC is on. It uses the shared format, with header `🖥️ <machine> · Heartbeat` and a fallback starting with the machine label. Content:
  - **Uptime and boot time:** uptime in the current style (`up 3 h 0 min`), plus boot time without seconds (`since 2026-10-11 09:14 CEST`).
  - **Local IP:** existing rules, but **IPv4 only**. The heartbeat never shows IPv6, even when `include_ipv6` is on for other messages.
  - **Users:** the existing logged-in-users list.
  - **Top 5 processes by current CPU use:**
    - name (truncated), PID, user, CPU % and memory %
    - measured by sampling `/proc` over about 1 s, not from a single `ps` reading (a lifetime average)
    - HostWatch's own process is excluded
    - shown as a monospace block so the columns line up on mobile
- **Schedule:** a systemd system timer `hostwatch-heartbeat.timer` with a oneshot `hostwatch-heartbeat.service`.
  - It runs relative to boot: the first heartbeat comes one interval after boot (`OnBootSec`), then one every interval (`OnUnitActiveSec`).
  - The interval comes from `[heartbeat] interval_minutes` (default 60, allowed 5–1440), and `install.sh` applies it to the timer.
- **Turning it off:** `[heartbeat] enabled = false` silences heartbeats without uninstalling. It takes effect at the next tick, with no reinstall. Boot, login and shutdown notifications keep working.
- **Delivery:** one attempt with a short (5 s) HTTP timeout. A failure is logged to the journal under `hostwatch` and skipped. Missed heartbeats are never queued or resent.
- **System-wide:** root-owned system units, so the heartbeat works whoever is logged in, including non-admin users, with no per-user setup. Non-admins can't stop, disable or edit it. The webhook stays in the root-only (600) config.
- **Light on resources:** a run takes a few seconds (about 1 s of that is the CPU sample), runs at low CPU and I/O priority, and is hard-capped by a start timeout.
- `install.sh` / `uninstall.sh` add and remove the timer, the service and the interval drop-in. `config.example.ini` and the README document the heartbeat.

Already in place and reused unchanged: the machine label and `machine_name`, header and fallback rules, logged-in users (logind with `who` fallback), local address rules, uptime formatting.

Assumptions:
- The request text was cut off after "a run finishes within a few seconds and uses". The resource limits above (low priority, start timeout) and the acceptance checks in tasks.md are my reading of the intent.
- As agreed, link-local `169.254.x.x` addresses are not filtered.

Out of scope: per-machine channels, a dashboard, other periodic reports (disk, temperatures), suspend/hibernate handling.

## Capabilities

### New Capabilities
- `heartbeat-notification`: The periodic alive message: its schedule relative to boot, the configurable interval, turning it off, its content (uptime, boot time, IPv4-only addresses, users, top processes from CPU sampling), single-attempt delivery and system-wide operation.

### Modified Capabilities
- `message-identity`: The shared format allows optional full-width sections after the fields (used for the process table). A message type may narrow the address rules (the heartbeat shows IPv4 only).
- `slack-delivery`: The retry policy names the heartbeat as a single-attempt message.
- `hostwatch-config`: The supported settings include `[heartbeat] enabled` and `interval_minutes`.
- `service-installation`: Install and uninstall manage the heartbeat timer and service, and install applies the configured interval.

## Impact

- **Code:**
  - new `src/hostwatch/processes.py` (CPU sampling)
  - a `heartbeat` subcommand and a hidden `heartbeat-interval` helper in `cli.py`
  - a `heartbeat_message` builder and section support in `messages.py`
  - `config.py` (heartbeat settings) and `timefmt.py` (boot time without seconds)
- **New files:** `systemd/hostwatch-heartbeat.timer` and `systemd/hostwatch-heartbeat.service`.
- **Scripts:** `install.sh` writes `/etc/systemd/system/hostwatch-heartbeat.timer.d/interval.conf`. `uninstall.sh` removes it.
- **Host:** one more timer. With the default interval that's 24 Slack messages per day per machine.
- **Network:** each heartbeat is one HTTPS request to the Slack webhook. Nothing else.
