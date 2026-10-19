# Spec Delta

## MODIFIED Requirements

### Requirement: Heartbeat message content
The heartbeat SHALL carry the common identification defined by message-identity, with the event `Heartbeat`. Its own fields SHALL be the uptime, for example `up 3 h 0 min`, the boot time with date, hours, minutes and timezone, for example `since 2026-10-11 09:14 CEST`, and, when the daily summary is enabled and could be computed, uptime today (per the uptime-summary capability) including the running session up to now, for example `5 h 42 min (2 sessions)`; omitted when the daily summary is disabled or could not be computed. It SHALL end with the top-processes table. Gathering this information SHALL NOT send any network request.

#### Scenario: Typical heartbeat
- **WHEN** host `office-pc`, booted at 09:14 CEST, sends its heartbeat at 12:14
- **THEN** the header reads `🖥️ office-pc · Heartbeat`, the fallback starts with `office-pc · `, and the message shows `up 3 h 0 min`, `since 2026-10-11 09:14 CEST`, the local addresses, the users and the process table

#### Scenario: Uptime today across reboots
- **WHEN** the host booted at 08:00, rebooted at 10:00, booted again, and a heartbeat runs at 11:00
- **THEN** the heartbeat shows session uptime of about 1 hour and "Uptime today" of about 3 hours across 2 sessions

#### Scenario: Daily summary unavailable
- **WHEN** the ledger or last-alive timestamp cannot be read or updated during a heartbeat run
- **THEN** the heartbeat is still sent with its existing uptime and since fields, without an "Uptime today" field, and the journal records why
