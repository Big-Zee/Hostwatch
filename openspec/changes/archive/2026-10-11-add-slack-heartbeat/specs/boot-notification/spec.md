# Spec Delta

## Purpose

Announces in Slack that the host has finished booting, with when it happened and how the host can be reached, without ever delaying or breaking boot.

## ADDED Requirements

### Requirement: One notification per boot after the network is up
The service SHALL send exactly one boot notification per boot. It SHALL send it after the system reports the network online.

#### Scenario: Normal boot
- **WHEN** the PC boots and the network comes online
- **THEN** exactly one boot message appears in the Slack channel

### Requirement: Boot message content
The boot message SHALL contain:
- the date and time it was produced, formatted `YYYY-MM-DD HH:MM:SS TZ` in the configured display timezone
- the kernel boot time in the same format
- the hostname
- the local IP addresses of active interfaces
- the public IP address, or a status saying it is disabled or unavailable

#### Scenario: Content of a typical message
- **WHEN** host `my-pc` with Wi-Fi address `192.168.1.20` boots and the public IP lookup succeeds
- **THEN** the message shows a time like `2026-10-11 12:01:33 CEST`, hostname `my-pc`, local IP `192.168.1.20` with its interface name, and the public IP

### Requirement: Local addresses exclude loopback and virtual interfaces
Local IP addresses SHALL include only interfaces that are up. Loopback SHALL be excluded, along with interfaces whose names match the configured skip prefixes (docker, bridges, veth, libvirt, LXC/LXD, tun/tap, VPN overlays). IPv6 global addresses SHALL be included only when enabled in the configuration.

#### Scenario: Docker installed
- **WHEN** the host has `lo`, `enp3s0`, `docker0` and `veth1a2b` up
- **THEN** only the address of `enp3s0` is listed

#### Scenario: No usable interface
- **WHEN** no qualifying interface has an address
- **THEN** the message states that no local address was found and is still sent

### Requirement: Public IP lookup is optional and never blocks the message
When the public IP lookup is enabled, the service SHALL query the configured service with a short timeout. If the lookup fails or times out, the message SHALL still be sent, showing the public IP as unavailable. When the lookup is disabled, no external lookup request SHALL be made.

#### Scenario: Lookup service unreachable
- **WHEN** the public IP service times out
- **THEN** the boot message is sent with the public IP shown as unavailable

#### Scenario: Lookup disabled
- **WHEN** the public IP lookup is disabled in the configuration
- **THEN** no request is made to the lookup service and the message shows the public IP as disabled

### Requirement: Boot is never delayed or broken
The boot notification SHALL NOT delay the system reaching its normal boot target. Failure of the notification SHALL NOT mark boot as degraded.

#### Scenario: Offline boot
- **WHEN** the PC boots with no network
- **THEN** boot completes in its usual time, the service retries in the background, then logs the failure to the journal, and no failed unit is reported
