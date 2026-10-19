# Spec Delta

## MODIFIED Requirements

### Requirement: Shutdown message content
The shutdown message SHALL carry the common identification defined by message-identity, with the shutdown event type ("Shutting down" or "Rebooting") as its event. Its own fields SHALL be:
- the date and time, formatted `YYYY-MM-DD HH:MM:SS TZ` in the configured display timezone
- the uptime, as days, hours and minutes, for example `up 5 h 12 min`
- when the daily summary is enabled and could be computed, uptime today (per the uptime-summary capability) including the session now ending, for example `5 h 42 min (2 sessions)`; omitted when the daily summary is disabled or could not be computed

Gathering this information SHALL NOT send any network request.

#### Scenario: Typical message
- **WHEN** host `my-pc` at `enp3s0: 192.168.1.20`, up for 5 hours 12 minutes with `alice` logged in on the desktop, is powered off
- **THEN** the header reads `🖥️ my-pc · Shutting down`, and the message shows the time, `up 5 h 12 min`, `enp3s0: 192.168.1.20` and `alice` as desktop

#### Scenario: Long uptime
- **WHEN** the host has been up for 2 days, 3 hours and 4 minutes
- **THEN** the uptime reads `up 2 d 3 h 4 min`

#### Scenario: Uptime today includes the ending session
- **WHEN** the host booted at 08:00, was shut down cleanly at 10:00 the same day, with no other boot session today
- **THEN** the shutdown message shows "Uptime today" as about 2 hours across 1 session, including the session that is ending

#### Scenario: Daily summary unavailable
- **WHEN** the ledger cannot be read or updated during shutdown
- **THEN** the shutdown message is still sent with the existing time and uptime fields, without an "Uptime today" field, and the journal records why
