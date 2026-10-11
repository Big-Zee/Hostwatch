# Design

## Context

For motivation see proposal.md (Why); for behavior see `specs/`. The current pieces this builds on:
- **Boot unit** `hostwatch-boot.service`: `Type=simple`, `After=`/`Wants=network-online.target`, with `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` and `NoNewPrivileges`. The CLI's `boot` command builds its payload in a closure that is rebuilt on each retry (`slack.BOOT_DELAYS`).
- `slack.post(webhook, payload, delays, timeout=10)`: the number of attempts is `len(delays) + 1`. Network errors, 429 and 5xx are retried.
- `netinfo.local_addresses()` and `messages.boot_message()` already produce the `iface: addr` local IP field.
- There is no state directory yet.

## Goals / Non-Goals

**Goals:**
- One message per real poweroff, halt or reboot, sent before the network stops.
- A hard upper bound of about 10 s on shutdown delay, with no false "clean" or "unclean" verdicts.

**Non-Goals:**
- Delivering shutdown messages that failed later (no queue).
- Suspend/hibernate.
- Telling apart a hard reset from a kernel panic or power loss. All three are "not clean".

## Decisions

### D1. A separate `hostwatch-shutdown.service`, not the boot unit
The shutdown hook needs `Type=oneshot` + `RemainAfterExit=yes`, so that the unit is "active" from boot and its `ExecStop=` runs at shutdown. The boot unit is deliberately `Type=simple`, because the targets that want a unit wait for it: with `oneshot`, `multi-user.target` would wait for up to about 2.5 min of boot retries. Merging the two would bring that back or force a rewrite of the boot path. Separate units also keep the jobs independent:
- a failed boot delivery cannot affect whether the shutdown hook is armed
- each unit has its own timeouts and journal stream (`journalctl -u hostwatch-shutdown`)

```ini
[Unit]
Description=Slack notification when the host shuts down or reboots (HostWatch)
Wants=network-online.target
After=network-online.target nss-lookup.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true
ExecStop=/usr/local/bin/hostwatch shutdown
TimeoutStopSec=10
StateDirectory=hostwatch
SyslogIdentifier=hostwatch
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

**Ordering.** systemd stops units in the reverse of their start order. Because this unit is `After=network-online.target`, it is stopped before network-online.target, and so before NetworkManager/networkd go down. `nss-lookup.target` is added so that systemd-resolved, and with it DNS, is still running too. Default dependencies give `Conflicts=`/`Before=shutdown.target`, so the stop job runs on every shutdown.

### D2. Only real shutdowns send (guard against `stop` / `restart`)
`ExecStop=` also runs on `systemctl stop|restart`, on `daemon-reexec` restarts and when uninstalling. Before doing anything, `hostwatch shutdown` checks `systemctl is-system-running`:
- **`stopping`**: a real shutdown, so proceed.
- **Anything else**: log "not a system shutdown, skipping" and exit 0, without writing the marker or sending.

`install.sh` uses `systemctl enable --now`, which starts the unit only if it is inactive and never restarts it. `uninstall.sh` runs `systemctl disable --now`, which hits the guard and sends nothing.

### D3. Detecting reboot vs poweroff
While shutting down, systemd's job queue holds the target. `hostwatch shutdown` runs `systemctl list-jobs --no-legend --plain` with a 2 s timeout and maps the result:

| Target in the job queue | Message |
|---|---|
| `reboot.target`, `kexec.target`, `soft-reboot.target` | "Rebooting" |
| `poweroff.target`, `halt.target` | "Shutting down" |
| anything else, nothing, or an error | "Shutting down" |

Alternatives considered:
- `/run/systemd/shutdown/scheduled` only exists for *scheduled* shutdowns.
- Parsing `/proc/cmdline` doesn't help.
- The D-Bus `PreparingForShutdown` signal doesn't distinguish the two and needs a running listener.

### D4. Timing budget
The command proceeds in this order, all bounded:
1. Guard check (`is-system-running`, about 2 s timeout).
2. Write the marker (D5).
3. Target detection (about 2 s timeout).
4. Local IPs (`ip -j`, already has a 5 s timeout, normally milliseconds).
5. One `slack.post(..., delays=(), timeout=5)`.

`TimeoutStopSec=10` is the hard cap. It matters because Python's socket timeout doesn't cover `getaddrinfo`, so a hung DNS lookup could exceed 5 s. systemd then kills the process and shutdown continues. Because the marker is written first, the kill doesn't turn a clean shutdown into an "unclean" one.

`slack.post` already supports one attempt with `delays=()`. The CLI passes `timeout=5` for this event. That needs a new `SHUTDOWN_TIMEOUT = 5` constant and threading `timeout` through `_deliver`.

### D5. Marker file and its life cycle (`src/hostwatch/state.py`)
The marker is `STATE_DIR = /var/lib/hostwatch` (overridable by `HOSTWATCH_STATE_DIR` for tests), file `clean_shutdown`, empty.

- **`mark_clean()`:** called by the shutdown command after the guard passes. It writes the file and fsyncs it plus the directory, so it survives the poweroff right after.
- **`consume_clean()`:** called by the boot command *first*, before loading the config. It returns whether the file existed and removes it.
  - Doing it before the config load means a broken config can't leave a stale marker that would hide a later crash.
  - A dry run calls `peek_clean()` instead, which never removes the file.
- **`install.sh`:** creates `/var/lib/hostwatch` (0755) and writes the marker, so the first boot after install isn't flagged.
  - Reinstalling over a running system writes the marker again. That is acceptable: if the previous session crashed, the boot that followed has already reported it and consumed the marker.

Both units declare `StateDirectory=hostwatch`, because `ProtectSystem=strict` makes `/var/lib` read-only unless the unit asks for it. systemd creates the directory if it is missing.

| Situation at boot | Marker present? | Warning |
|---|---|---|
| After a clean poweroff/reboot | yes | no |
| After power loss / crash / reset | no | yes |
| First boot after install | yes (written by install.sh) | no |
| Second crash in a row | no (consumed by the previous boot) | yes |

### D6. Messages
- **Shutdown:**
  - header `:red_circle: my-pc is shutting down` or `:arrows_counterclockwise: my-pc is rebooting`
  - fields: Event, Time, Host, Local IP (same `iface: addr` rendering and `_no local IP_` fallback, so this is factored out of `boot_message`), Uptime
  - fallback text: `my-pc is shutting down at <time> (up 5 h 12 min)`
- **Uptime:** read from `/proc/uptime` and formatted as `up [D d ]H h M min`. Leading zero units are dropped (`up 12 min`, `up 0 min`).
- **Boot warning:** a section block with `:warning: Previous shutdown was not clean (power loss or crash?)` is placed before the fields. ` – previous shutdown was not clean` is appended to the fallback text, so it shows in push previews.

## Risks / Trade-offs

- [NetworkManager or Wi-Fi may already be tearing down for reasons outside unit ordering, for example user-session Wi-Fi with a per-user secret] → The ordering covers system connections. For the rest, a single failed attempt is logged and accepted. The README notes that system-wide connections are needed.
- [`systemctl is-system-running` returns `stopping` only during shutdown; an edge case like `systemctl isolate rescue.target` stops the unit without sending] → Intended: that isn't a poweroff/reboot.
- [A hard reset during the roughly 10 s shutdown window, after the marker is written, is reported as clean] → Accepted: the shutdown was intended. It is a very small window.
- [Reinstalling after an unreported crash hides it] → Only if install runs before the post-crash boot message, which is impossible because the boot happens first.
- [The shutdown unit stays active and does nothing for the whole uptime] → It costs nothing. `ExecStart=/bin/true`.

## Migration Plan

Nothing is installed yet, so the first install includes this. On a host installed before this change, rerunning `install.sh` adds the unit, the state directory and the marker. The next shutdown is announced without a reboot, because the unit is started with `--now`.
