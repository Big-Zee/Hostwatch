# Spec Delta

## MODIFIED Requirements

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
