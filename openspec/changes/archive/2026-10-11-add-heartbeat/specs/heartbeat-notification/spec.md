# Spec Delta

## Purpose

Sends a periodic heartbeat to Slack while the PC is on, showing that it is alive, how long it has been up, who is logged in and what is using the CPU, without ever queuing or resending missed heartbeats.

## ADDED Requirements

### Requirement: Heartbeat schedule relative to boot
While the system runs, the service SHALL send a heartbeat every configured interval, measured from boot rather than the wall clock. The first heartbeat SHALL come one interval after boot. The interval SHALL default to 60 minutes.

#### Scenario: Default schedule
- **WHEN** the PC boots at 09:14 with the default settings and stays on
- **THEN** heartbeats arrive at about 10:14, 11:14, 12:14, and so on

#### Scenario: Custom interval
- **WHEN** `interval_minutes = 30` is configured and `install.sh` has been run
- **THEN** heartbeats arrive about every 30 minutes, the first about 30 minutes after boot

### Requirement: Heartbeat can be turned off
When the heartbeat is disabled in the configuration, no heartbeat SHALL be sent, starting with the next scheduled run, without reinstalling. Boot, shutdown and login notifications SHALL keep working.

#### Scenario: Disabled
- **WHEN** `enabled = false` is set under `[heartbeat]`
- **THEN** no further heartbeat messages are sent, and the next login still sends a login message

### Requirement: Heartbeat message content
The heartbeat SHALL carry the common identification defined by message-identity, with the event `Heartbeat`. Its own fields SHALL be the uptime, for example `up 3 h 0 min`, and the boot time with date, hours, minutes and timezone, for example `since 2026-10-11 09:14 CEST`. It SHALL end with the top-processes table. Gathering this information SHALL NOT send any network request.

#### Scenario: Typical heartbeat
- **WHEN** host `office-pc`, booted at 09:14 CEST, sends its heartbeat at 12:14
- **THEN** the header reads `🖥️ office-pc · Heartbeat`, the fallback starts with `office-pc · `, and the message shows `up 3 h 0 min`, `since 2026-10-11 09:14 CEST`, the local addresses, the users and the process table

### Requirement: Heartbeat shows IPv4 addresses only
The heartbeat's local addresses SHALL follow the boot-notification rules, except that IPv6 addresses SHALL never be shown, whatever the IPv6 setting is. When no IPv4 address qualifies, the field SHALL read "no local IP" and the heartbeat SHALL still be sent.

#### Scenario: IPv6 enabled for other messages
- **WHEN** `include_ipv6 = true` and `enp3s0` has `192.168.1.20` and a global IPv6 address
- **THEN** the heartbeat lists only `enp3s0: 192.168.1.20`

#### Scenario: No IPv4 address
- **WHEN** no qualifying interface has an IPv4 address
- **THEN** the heartbeat shows "no local IP" and is sent

### Requirement: Top processes by current CPU use
The heartbeat SHALL list the five processes using the most CPU over a sampling window of one to two seconds, not their lifetime average. Each row SHALL show PID, user, CPU %, memory % and the process name, truncated to fit. HostWatch's own process SHALL be excluded. The table SHALL be a monospace block with aligned columns.

#### Scenario: Busy process
- **WHEN** a process has been idle for hours and is now using a full core
- **THEN** it appears at the top of the table with a CPU % near 100

#### Scenario: Own process excluded
- **WHEN** the heartbeat samples processes
- **THEN** the HostWatch process taking the sample does not appear in the table

### Requirement: Missed heartbeats are not queued
Each heartbeat SHALL make a single delivery attempt with a short timeout. When delivery fails, the failure SHALL be logged to the systemd journal under the identifier `hostwatch` and the heartbeat SHALL be dropped. Missed heartbeats SHALL NOT be stored, retried later or sent in bulk.

#### Scenario: Slack unreachable for two hours
- **WHEN** Slack cannot be reached for two hours and then recovers
- **THEN** the journal shows the failed heartbeats, and after recovery only the next scheduled heartbeat is sent, with no backlog

### Requirement: Heartbeat runs system-wide with bounded resources
The heartbeat SHALL run as a root-owned system service that works whoever is logged in, including non-administrators, with no per-user setup. Non-administrators SHALL NOT be able to stop, disable or change it. A run SHALL finish within a few seconds and run at reduced CPU and I/O priority.

#### Scenario: Non-admin user
- **WHEN** a non-administrator runs `systemctl stop hostwatch-heartbeat.timer`
- **THEN** the request is refused and heartbeats continue

#### Scenario: Short run
- **WHEN** a heartbeat runs on an idle machine with Slack reachable
- **THEN** the service finishes within a few seconds
