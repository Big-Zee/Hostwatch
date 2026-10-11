# Proposal

## Why

HostWatch reports when the PC comes up and who logs in, but not when it goes down. Without a shutdown message you can't tell from the channel whether a PC that is silent was switched off, rebooted or crashed. A crash or power loss can't announce itself, so the next boot has to report it.

## What Changes

- **Shutdown notification:** on a clean poweroff, halt or reboot, HostWatch sends one Slack message containing:
  - the event: "Shutting down" or "Rebooting". This is read from the pending systemd shutdown target. Anything unknown falls back to "Shutting down".
  - date and time in the configured display timezone
  - hostname
  - local IP addresses, with the same rules and format as the boot message
  - uptime, for example `up 5 h 12 min`
- **Shutdown is never noticeably delayed:**
  - one delivery attempt with a 5 s HTTP timeout and no retries
  - the unit is hard-capped at about 10 s (`TimeoutStopSec`)
  - a failure is logged to the journal and shutdown continues
- **Clean-shutdown marker:** a clean shutdown writes `/var/lib/hostwatch/clean_shutdown` *before* trying to send, so a slow or failed send never makes the shutdown look unclean.
- **Unclean-shutdown warning:** on boot, HostWatch consumes the marker. If it was missing, the boot message carries the warning "Previous shutdown was not clean (power loss or crash?)". `install.sh` writes the marker, so the first boot after installing does not warn.
- **New unit `hostwatch-shutdown.service`:**
  - `Type=oneshot`, `RemainAfterExit=yes`, ordered after `network-online.target`, so it is stopped (and sends) before the network goes down
  - its stop action does nothing unless the system really is shutting down, so `systemctl restart`, `stop` or reinstalls send nothing
  - the existing boot unit is unchanged apart from gaining write access to the state directory
- **`install.sh` / `uninstall.sh`:**
  - install creates `/var/lib/hostwatch`, writes the initial marker, and enables and starts the shutdown unit
  - uninstall stops and removes the unit and deletes `/var/lib/hostwatch`
- The README covers the shutdown message, the unclean-shutdown warning and troubleshooting.

Out of scope: suspend/hibernate notifications, hourly reports, a persistent queue for messages that could not be sent at shutdown.

## Capabilities

### New Capabilities
- `shutdown-notification`: Announcing clean poweroff/reboot in Slack with event type, time, host, local addresses and uptime, without delaying shutdown. Also recording that the shutdown was clean.

### Modified Capabilities
- `boot-notification`: The boot message warns when the previous shutdown was not clean. Checking the marker never sends a network request and never blocks the message.
- `slack-delivery`: The retry requirement now allows a per-event policy. Boot and login retry with backoff. Shutdown makes a single short attempt.
- `service-installation`: Install and uninstall manage the shutdown unit and the state directory. The first boot after install produces no false warning.

## Impact

- **Code:**
  - new: `shutdown` subcommand in `src/hostwatch/cli.py`, a shutdown message builder in `messages.py`, a small `state` module for the marker
  - `netinfo.py` / `timefmt.py`: shutdown-target detection and uptime formatting
- **New files:** `systemd/hostwatch-shutdown.service`. The boot unit gains `StateDirectory=hostwatch`.
- **Scripts:** `install.sh`, `uninstall.sh`.
- **Docs and tests:** README, tests for the new builders, marker handling, target detection and uptime.
- **Host:** a new directory `/var/lib/hostwatch` (root, 0755) holding one empty marker file. One more enabled unit.
- **Network:** at shutdown, one HTTPS request to the Slack webhook.
