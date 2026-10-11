# message-identity Specification

## Purpose

Makes every HostWatch message identify the machine it comes from and show its local addresses and current users, in one consistent format, so a single Slack channel can serve several PCs.

## Requirements

### Requirement: Machine label
Each message SHALL identify the machine by a label. When a friendly machine name is configured and differs from the hostname, the label SHALL be `<machine name> (<hostname>)`. Otherwise the label SHALL be the hostname alone.

#### Scenario: Friendly name configured
- **WHEN** the machine name is set to `Office PC` on host `office-pc`
- **THEN** every message labels the machine `Office PC (office-pc)`

#### Scenario: No friendly name
- **WHEN** no machine name is configured on host `office-pc`
- **THEN** every message labels the machine `office-pc`

### Requirement: Header starts with the machine
The header of every message SHALL start with a computer icon followed by the machine label, then a separator and the event, for example `🖥️ office-pc · Boot`.

#### Scenario: Boot header
- **WHEN** host `office-pc` without a machine name sends its boot message
- **THEN** the header reads `🖥️ office-pc · Boot`

#### Scenario: Header with machine name
- **WHEN** `Office PC (office-pc)` is rebooting
- **THEN** the header reads `🖥️ Office PC (office-pc) · Rebooting`

### Requirement: Fallback text starts with the machine
The plain-text fallback of every message, used for push notifications and previews, SHALL start with the machine label followed by ` · ` and a one-line summary of the event.

#### Scenario: Two machines in one channel
- **WHEN** `office-pc` and `home-pc` both post boot messages to the same channel
- **THEN** the push previews start with `office-pc · ` and `home-pc · ` respectively, so the machines can be told apart without opening Slack

### Requirement: Every message shows local addresses and logged-in users
Every message type SHALL include the machine's local IP addresses, chosen and formatted by the boot-notification rules (`interface: address`, or "no local IP"), unless the message type narrows those rules. It SHALL also include the currently logged-in users as defined by the logged-in-users capability. This information SHALL be gathered without network requests.

#### Scenario: Login message includes addresses and users
- **WHEN** a login message is sent from a host at `enp3s0: 192.168.1.20` with a desktop session open
- **THEN** the message lists `enp3s0: 192.168.1.20` and the desktop session's user

#### Scenario: Test message includes addresses and users
- **WHEN** `hostwatch test` is run
- **THEN** the test message shows the machine label, the local addresses and the logged-in users

#### Scenario: Message type narrows the address rules
- **WHEN** a heartbeat is sent with IPv6 addresses enabled in the configuration
- **THEN** it shows only IPv4 addresses, as heartbeat-notification requires, while other message types still show IPv6

### Requirement: One shared message format
All message types SHALL be built by one shared format:
- a header as above
- an optional notice line
- labelled fields: the event's own fields first, then local addresses and logged-in users
- optional full-width sections after the fields, such as a table
- a footer naming HostWatch

A separate host field SHALL NOT be shown, because the header carries the machine label.

#### Scenario: Consistent layout
- **WHEN** a boot, a shutdown, a login, a test and a heartbeat message are compared
- **THEN** each has the same header pattern, each ends its fields with Local IP and Users, and each has the HostWatch footer

#### Scenario: Full-width section
- **WHEN** a heartbeat with its process table is built
- **THEN** the table follows the fields as its own full-width section, before the footer

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
