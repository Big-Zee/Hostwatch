# Spec Delta

## MODIFIED Requirements

### Requirement: Heartbeat schedule relative to boot
While the system runs, the service SHALL send a heartbeat every configured interval, measured from boot rather than the wall clock. The first heartbeat SHALL come one interval after boot, without any manual action after the reboot. The interval SHALL default to 60 minutes. After the install script applies an interval, the next heartbeat SHALL come one interval after the install, then every interval.

#### Scenario: Default schedule
- **WHEN** the PC boots at 09:14 with the default settings and stays on
- **THEN** heartbeats arrive at about 10:14, 11:14, 12:14, and so on

#### Scenario: Custom interval
- **WHEN** `interval_minutes = 30` is configured and `install.sh` has been run
- **THEN** heartbeats arrive about every 30 minutes, the first about 30 minutes after boot

#### Scenario: Scheduled right after boot
- **WHEN** the host has just booted and nobody has started any HostWatch unit by hand
- **THEN** `systemctl list-timers hostwatch-heartbeat.timer` shows a NEXT time no more than one interval away, and the first heartbeat arrives about one interval after boot

#### Scenario: Short interval after reboot
- **WHEN** `interval_minutes = 5` is configured, `install.sh` has been run, and the host is rebooted
- **THEN** the first heartbeat arrives about 5 minutes after boot and the next ones about every 5 minutes

#### Scenario: Install on a long-running host
- **WHEN** `install.sh` applies a new interval of 60 minutes on a host that has been up for 3 hours
- **THEN** no heartbeat is sent at once, and the next heartbeat arrives about 60 minutes after the install
