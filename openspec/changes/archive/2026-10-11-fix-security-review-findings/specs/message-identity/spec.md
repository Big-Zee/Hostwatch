# Spec Delta

## ADDED Requirements

### Requirement: Host values are shown literally
Values that come from the host rather than from HostWatch SHALL be shown literally in every part of a message, including the plain-text fallback. This covers process names, user names, remote hosts, terminals, interface names and the machine label. Such a value SHALL NOT create a Slack mention, link or text formatting, and SHALL NOT end the process table's monospace block.

#### Scenario: Process name crafted to ping the channel
- **WHEN** an unprivileged user runs a busy process named ```` ```<!channel> ```` and a heartbeat is sent
- **THEN** the process appears in the table with its name shown as text, the table stays one monospace block, and nobody in the channel is notified

#### Scenario: Special characters in the fallback
- **WHEN** the machine name is set to `Lab <A&B>`
- **THEN** the push preview and the header both show `Lab <A&B>` as text

#### Scenario: Ordinary values unchanged
- **WHEN** host `office-pc` sends a heartbeat listing process `firefox` run by `alice`
- **THEN** the message looks exactly as before this requirement
