# Spec Delta

## Purpose

Makes every HostWatch message identify the machine it comes from and show its local addresses and current users, in one consistent format, so a single Slack channel can serve several PCs.

## ADDED Requirements

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
Every message type SHALL include the machine's local IP addresses, chosen and formatted by the boot-notification rules (`interface: address`, or "no local IP"). It SHALL also include the currently logged-in users as defined by the logged-in-users capability. This information SHALL be gathered without network requests.

#### Scenario: Login message includes addresses and users
- **WHEN** a login message is sent from a host at `enp3s0: 192.168.1.20` with a desktop session open
- **THEN** the message lists `enp3s0: 192.168.1.20` and the desktop session's user

#### Scenario: Test message includes addresses and users
- **WHEN** `hostwatch test` is run
- **THEN** the test message shows the machine label, the local addresses and the logged-in users

### Requirement: One shared message format
All message types SHALL be built by one shared format:
- a header as above
- an optional notice line
- labelled fields: the event's own fields first, then local addresses and logged-in users
- a footer naming HostWatch

A separate host field SHALL NOT be shown, because the header carries the machine label.

#### Scenario: Consistent layout
- **WHEN** a boot, a shutdown, a login and a test message are compared
- **THEN** each has the same header pattern, each ends its fields with Local IP and Users, and each has the HostWatch footer
