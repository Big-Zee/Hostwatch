# Spec Delta

## MODIFIED Requirements

### Requirement: Boot message content
The boot message SHALL contain:
- the date and time it was produced, formatted `YYYY-MM-DD HH:MM:SS TZ` in the configured display timezone
- the kernel boot time in the same format
- the hostname
- the local IP addresses of active interfaces

#### Scenario: Content of a typical message
- **WHEN** host `my-pc` with Wi-Fi interface `wlp2s0` at `192.168.1.20` boots
- **THEN** the message shows a time like `2026-10-11 12:01:33 CEST`, hostname `my-pc` and local IP `wlp2s0: 192.168.1.20`, and contains no address obtained from outside the machine

### Requirement: Local addresses exclude loopback and virtual interfaces
Local IP addresses SHALL include only interfaces that are up. Loopback interfaces and any address in `127.0.0.0/8` SHALL be excluded, along with interfaces whose names match the configured skip prefixes (docker, bridges, veth, libvirt, LXC/LXD, tun/tap, VPN overlays). Each address SHALL be shown with its interface name as `interface: address`. IPv6 global addresses SHALL be included only when enabled in the configuration.

#### Scenario: Docker installed
- **WHEN** the host has `lo`, `enp3s0`, `docker0` and `veth1a2b` up
- **THEN** only the address of `enp3s0` is listed

#### Scenario: Ethernet and Wi-Fi both connected
- **WHEN** `enp3s0` has `192.168.1.20` and `wlp2s0` has `192.168.1.35`, both up
- **THEN** the message lists `enp3s0: 192.168.1.20` and `wlp2s0: 192.168.1.35`, one per line

#### Scenario: Loopback address on another interface
- **WHEN** an up, non-skipped interface carries `127.0.1.1`
- **THEN** that address is not listed

#### Scenario: No usable interface
- **WHEN** no qualifying interface has an address
- **THEN** the local IP field reads "no local IP" and the message is still sent

## REMOVED Requirements

### Requirement: Public IP lookup is optional and never blocks the message
**Reason**: The host only needs to be identified on the local network. The external lookup added a third-party dependency, a request outside the LAN on every boot, and extra delay when the internet was slow or down.
**Migration**: None needed. The related settings are ignored if still present in the config (see `hostwatch-config`). Use the local addresses in the boot message.

## ADDED Requirements

### Requirement: Boot information is gathered without network requests
Collecting the information shown in the boot message SHALL NOT send any network request. The Slack webhook delivery SHALL be the only outbound connection the boot notification makes.

#### Scenario: Only Slack is contacted
- **WHEN** the host boots with internet access and outbound connections are observed (for example with `ss` or `tcpdump`)
- **THEN** the only connection HostWatch opens is to the Slack webhook host, and the boot message arrives within seconds of the network coming online
