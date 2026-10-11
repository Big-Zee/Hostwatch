# Spec Delta

## MODIFIED Requirements

### Requirement: Shutdown message content
The shutdown message SHALL carry the common identification defined by message-identity, with the shutdown event type ("Shutting down" or "Rebooting") as its event. Its own fields SHALL be:
- the date and time, formatted `YYYY-MM-DD HH:MM:SS TZ` in the configured display timezone
- the uptime, as days, hours and minutes, for example `up 5 h 12 min`

Gathering this information SHALL NOT send any network request.

#### Scenario: Typical message
- **WHEN** host `my-pc` at `enp3s0: 192.168.1.20`, up for 5 hours 12 minutes with `alice` logged in on the desktop, is powered off
- **THEN** the header reads `🖥️ my-pc · Shutting down`, and the message shows the time, `up 5 h 12 min`, `enp3s0: 192.168.1.20` and `alice` as desktop

#### Scenario: Long uptime
- **WHEN** the host has been up for 2 days, 3 hours and 4 minutes
- **THEN** the uptime reads `up 2 d 3 h 4 min`
