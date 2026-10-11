# Spec Delta

## MODIFIED Requirements

### Requirement: Boot message content
The boot message SHALL carry the common identification defined by message-identity, with the event `Boot`. Its own fields SHALL be:
- the date and time it was produced, formatted `YYYY-MM-DD HH:MM:SS TZ` in the configured display timezone
- the kernel boot time in the same format

#### Scenario: Content of a typical message
- **WHEN** host `my-pc` with Wi-Fi interface `wlp2s0` at `192.168.1.20` boots and nobody is logged in yet
- **THEN** the header reads `🖥️ my-pc · Boot`, and the message shows a time like `2026-10-11 12:01:33 CEST`, the kernel boot time, local IP `wlp2s0: 192.168.1.20` and "No users logged in", and contains no address obtained from outside the machine
