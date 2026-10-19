# uptime-summary Specification

## Purpose

Tracks boot sessions in a small on-disk ledger and turns them into a single "uptime today" figure that boot, shutdown and heartbeat messages can show, including an honest estimate after a crash or power loss.

## Requirements

### Requirement: Boot-session ledger
The service SHALL maintain a ledger of boot sessions under `/var/lib/hostwatch/`, owned by root with permissions `600`. Each entry SHALL record the boot time, the end time (when known) and the end reason: clean shutdown, reboot, or unclean (estimated). `hostwatch boot` SHALL append a new open entry for the current boot. `hostwatch shutdown` SHALL close the current entry with the real end time and reason when it runs for a genuine system shutdown or reboot.

#### Scenario: Entry opened at boot
- **WHEN** the host boots
- **THEN** the ledger gains a new entry with this boot's start time and no end time

#### Scenario: Entry closed at clean shutdown
- **WHEN** `sudo poweroff` or `sudo reboot` triggers the shutdown notification
- **THEN** the current entry is closed with the shutdown time and the matching reason (clean shutdown or reboot)

### Requirement: Last-alive timestamp for unclean shutdowns
The service SHALL maintain a "last alive" timestamp file, written atomically (temporary file then rename) to limit disk wear. A lightweight root-owned timer SHALL update it every `last_alive_interval_minutes` (default 5), and each heartbeat run SHALL also update it. On the next boot, an entry left open by a previous run (no clean close) SHALL be closed using this timestamp, with its end reason marked unclean and its duration marked as estimated.

#### Scenario: Power loss
- **WHEN** the host loses power and is booted again
- **THEN** the previous entry is closed using the last recorded "last alive" time, marked unclean and estimated, and the new boot still shows the existing unclean-shutdown warning

#### Scenario: Timestamp kept current while running
- **WHEN** the host has been running for several last-alive intervals and a heartbeat has just completed
- **THEN** the last-alive timestamp reflects a time no earlier than that heartbeat

### Requirement: Uptime-today calculation
A single shared function SHALL compute "uptime today": the total time the machine was powered on during the local calendar day from 00:00 to now, summed over every boot session (ledger entries plus the currently running session) that overlaps today. All message types SHALL use this one function rather than each computing it independently.

#### Scenario: Several sessions in a day
- **WHEN** the host booted at 08:00, rebooted at 10:00, booted again, and a heartbeat runs at 11:00
- **THEN** uptime today is about 3 hours across 2 sessions

#### Scenario: Session crossing midnight
- **WHEN** a session started yesterday and is still running after local midnight
- **THEN** only the portion of that session from 00:00 onward counts toward today

#### Scenario: Estimated session included
- **WHEN** today's total includes a session closed from the last-alive timestamp after an unclean shutdown
- **THEN** the figure is marked as estimated, for example `~5 h 40 min`, rather than shown as exact

### Requirement: Uptime-today result includes session count and estimation flag
The uptime-today calculation SHALL return, alongside the total duration, the number of sessions counted and whether any of them is estimated.

#### Scenario: Session count reported
- **WHEN** two boot sessions overlap today
- **THEN** the calculation reports a session count of 2 alongside the total duration

### Requirement: Formatted uptime-today text
The formatted "uptime today" text SHALL read as hours and minutes followed by the session count in parentheses, for example `5 h 42 min (2 sessions)`, and SHALL be prefixed with `~` when any counted session is estimated, for example `~5 h 40 min (2 sessions)`.

#### Scenario: Exact total
- **WHEN** uptime today is 5 hours 42 minutes across 2 sessions, none estimated
- **THEN** the text reads `5 h 42 min (2 sessions)`

#### Scenario: Estimated total
- **WHEN** uptime today includes one estimated session
- **THEN** the text is prefixed with `~`

### Requirement: Missing or corrupt ledger is treated as empty
A missing ledger (first run after install) SHALL be treated as empty, starting from the current boot, without logging a false unclean-shutdown condition. A corrupt or unreadable ledger SHALL be logged to the journal and treated as empty, rebuilding from the current boot; it SHALL NOT raise an error that fails a notification.

#### Scenario: First run after install
- **WHEN** no ledger file exists yet
- **THEN** uptime today is computed as if the ledger were empty, and no unclean-shutdown condition is logged because of the missing ledger

#### Scenario: Corrupt ledger
- **WHEN** the ledger file contains invalid data
- **THEN** the journal records the problem, the ledger is treated as empty for this run, and the boot, shutdown or heartbeat notification is still sent (with or without the summary line, per the delivery requirement below)

### Requirement: Negative durations are never produced
The calculation SHALL NOT produce a negative duration when the system clock or timezone has moved backward; any session whose duration cannot be computed as non-negative SHALL be excluded from the total rather than making it negative or raising an error.

#### Scenario: Clock moved backwards
- **WHEN** the system clock has moved backward since a session's recorded start
- **THEN** that session is excluded from uptime today rather than contributing a negative duration

### Requirement: Ledger access never delays a notification
Reading or updating the ledger, and reading or updating the last-alive timestamp, SHALL NOT delay boot, login or shutdown beyond their existing time limits. When the ledger cannot be read or updated for any reason, the affected notification SHALL still be sent without the uptime-today line, and the reason SHALL be logged to the journal.

#### Scenario: Ledger access fails during shutdown
- **WHEN** the ledger cannot be written during a shutdown notification
- **THEN** the shutdown message is still sent (with its existing session-uptime field) within the existing time limit, without the uptime-today field, and the journal records why

### Requirement: Concurrent ledger writers do not corrupt the ledger
Concurrent writers (a shutdown in progress, a heartbeat, and the last-alive timer, which can all run close together) SHALL NOT corrupt the ledger. Writes SHALL use a lock file or atomic replace so a reader never observes a partially written ledger.

#### Scenario: Heartbeat and last-alive timer overlap
- **WHEN** the last-alive timer fires while a heartbeat is also updating the last-alive timestamp
- **THEN** the resulting timestamp file is one complete, valid write, never a mix of both

### Requirement: Ledger retention
Ledger entries older than `retention_days` (default 90) SHALL be pruned. Pruning SHALL NOT remove the entry for the currently open session.

#### Scenario: Old entries pruned
- **WHEN** the ledger contains entries older than the configured retention period
- **THEN** those entries are removed the next time the ledger is written, and entries within the retention period are kept

### Requirement: Last-alive timer runs with bounded resources and cannot be disabled by non-admins
The last-alive timer SHALL run as a root-owned system timer and service, requiring no per-user setup, and SHALL NOT be stoppable or disableable by non-administrators. Each run SHALL finish quickly and SHALL only update the last-alive timestamp file.

#### Scenario: Non-admin user
- **WHEN** a non-administrator runs `systemctl stop hostwatch-last-alive.timer`
- **THEN** the request is refused and the timer keeps running
