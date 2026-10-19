# shutdown-notification Specification

## Purpose

Announces in Slack that the host is being powered off or rebooted, and records that the shutdown was clean, without ever noticeably delaying the shutdown.

## Requirements

### Requirement: One notification per clean shutdown or reboot
The service SHALL send exactly one shutdown notification when the system is cleanly powered off, halted or rebooted. Stopping or restarting HostWatch's own units while the system keeps running SHALL NOT send a notification.

#### Scenario: Poweroff
- **WHEN** `sudo poweroff` is run
- **THEN** exactly one shutdown message appears in the Slack channel before the host goes down

#### Scenario: Reboot
- **WHEN** `sudo reboot` is run
- **THEN** exactly one "Rebooting" message appears, followed after boot by the boot message

#### Scenario: Unit restarted while running
- **WHEN** an administrator restarts or stops the shutdown unit, or reinstalls HostWatch, while the system stays up
- **THEN** no shutdown message is sent

### Requirement: Shutdown event type
The message SHALL name the event as "Rebooting" when the system is rebooting and as "Shutting down" when it is powering off or halting. When the kind of shutdown cannot be determined, it SHALL say "Shutting down".

#### Scenario: Reboot detected
- **WHEN** the pending shutdown is a reboot
- **THEN** the message says "Rebooting"

#### Scenario: Unknown kind
- **WHEN** the kind of shutdown cannot be determined
- **THEN** the message says "Shutting down"

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

### Requirement: Shutdown is never noticeably delayed
The service SHALL make a single delivery attempt with a request timeout of about 5 seconds, and SHALL NOT retry. Its total time during shutdown SHALL be capped at about 10 seconds, after which the system SHALL continue shutting down. A failed delivery SHALL be logged to the journal.

#### Scenario: Slack unreachable at shutdown
- **WHEN** the host is powered off while Slack cannot be reached
- **THEN** shutdown takes at most about 10 seconds longer than without HostWatch, and the journal records the failed delivery

### Requirement: Clean shutdown is recorded before sending
On a clean shutdown the service SHALL record that the shutdown was clean before it attempts delivery. The record SHALL survive even if delivery fails, times out or is cut off.

#### Scenario: Delivery cut off
- **WHEN** delivery is still waiting when the shutdown time limit is reached
- **THEN** the shutdown is still recorded as clean and the next boot message carries no unclean-shutdown warning
