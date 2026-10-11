# boot-notification Specification

## Purpose

Announces in Slack that the host has finished booting, with when it happened and how the host can be reached, without ever delaying or breaking boot.

## Requirements

### Requirement: One notification per boot after the network is up
The service SHALL send exactly one boot notification per boot. It SHALL send it after the system reports the network online. Switching the system between targets while it runs SHALL NOT send another boot notification.

#### Scenario: Normal boot
- **WHEN** the PC boots and the network comes online
- **THEN** exactly one boot message appears in the Slack channel

#### Scenario: Switching targets while running
- **WHEN** an administrator runs `systemctl isolate multi-user.target`, `systemctl isolate graphical.target`, or isolates `rescue.target` and returns, without rebooting
- **THEN** no further boot message is sent, and the next boot message after a real reboot judges the previous shutdown correctly

### Requirement: Boot message content
The boot message SHALL carry the common identification defined by message-identity, with the event `Boot`. Its own fields SHALL be:
- the date and time it was produced, formatted `YYYY-MM-DD HH:MM:SS TZ` in the configured display timezone
- the kernel boot time in the same format

#### Scenario: Content of a typical message
- **WHEN** host `my-pc` with Wi-Fi interface `wlp2s0` at `192.168.1.20` boots and nobody is logged in yet
- **THEN** the header reads `🖥️ my-pc · Boot`, and the message shows a time like `2026-10-11 12:01:33 CEST`, the kernel boot time, local IP `wlp2s0: 192.168.1.20` and "No users logged in", and contains no address obtained from outside the machine

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

### Requirement: Boot is never delayed or broken
The boot notification SHALL NOT delay the system reaching its normal boot target. In particular, HostWatch SHALL NOT make the boot target wait for the network to come online. Failure of the notification, including an unexpected error in HostWatch itself, SHALL NOT mark boot as degraded.

#### Scenario: Offline boot
- **WHEN** the PC boots with no network
- **THEN** boot completes in its usual time, the service retries in the background, then logs the failure to the journal, and no failed unit is reported

#### Scenario: Boot target not held back by network-online
- **WHEN** the host boots with its network cable unplugged and `systemd-analyze critical-chain multi-user.target` is inspected
- **THEN** no HostWatch unit appears in the chain and the target is not reached later because of HostWatch

#### Scenario: Unexpected error during boot notification
- **WHEN** the boot notification hits an unexpected error, such as undecodable command output
- **THEN** the error is logged to the journal without exception text, nothing is sent, and the boot unit does not end in the failed state

### Requirement: Boot information is gathered without network requests
Collecting the information shown in the boot message SHALL NOT send any network request. The Slack webhook delivery SHALL be the only outbound connection the boot notification makes.

#### Scenario: Only Slack is contacted
- **WHEN** the host boots with internet access and outbound connections are observed (for example with `ss` or `tcpdump`)
- **THEN** the only connection HostWatch opens is to the Slack webhook host, and the boot message arrives within seconds of the network coming online

### Requirement: Boot message warns after an unclean shutdown
When the previous shutdown was not recorded as clean (power loss, crash, hard reset), the boot message SHALL carry the warning "Previous shutdown was not clean (power loss or crash?)", in the message and in its plain-text fallback. The clean-shutdown record SHALL be consumed on every boot, so each shutdown is judged once. A dry run SHALL NOT consume it.

#### Scenario: Power loss
- **WHEN** the host loses power and is booted again
- **THEN** the boot message contains the unclean-shutdown warning

#### Scenario: Clean reboot
- **WHEN** the host is rebooted with `sudo reboot`
- **THEN** the following boot message contains no warning

#### Scenario: Two crashes in a row are each reported
- **WHEN** the host crashes, boots (warning shown), and then crashes again before any clean shutdown
- **THEN** the next boot message shows the warning again

#### Scenario: Dry run leaves the record alone
- **WHEN** `hostwatch boot --dry-run` is run
- **THEN** the clean-shutdown record is neither read-and-removed nor changed
