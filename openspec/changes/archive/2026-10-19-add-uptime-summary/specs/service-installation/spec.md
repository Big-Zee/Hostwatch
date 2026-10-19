# Spec Delta

## MODIFIED Requirements

### Requirement: Install script sets up the service
Run as root from the repository, the install script SHALL:
- copy the program files to system locations
- create `/etc/hostwatch/config.ini` from `config.example.ini` with mode `600`
- create `/var/lib/hostwatch/` with correct ownership and permissions if it does not already exist
- enable the boot, shutdown and heartbeat notifications
- install and enable the last-alive timer, and verify with `systemctl list-timers` and `systemctl show -p TimersMonotonic` that it has a next run, the same way the heartbeat timer is already verified
- enable the login hook system-wide

It SHALL refuse to run without root privileges.

#### Scenario: Fresh install
- **WHEN** `sudo ./install.sh` is run on a fresh Ubuntu 24.04 host
- **THEN** the boot and shutdown notifications are enabled, the heartbeat timer and the last-alive timer are both enabled, active and shown to have a next run, the login hook is active, and the configuration file exists with mode `600`

#### Scenario: Not root
- **WHEN** `./install.sh` is run without root privileges
- **THEN** it exits with an error and changes nothing

#### Scenario: Last-alive timer has no next run
- **WHEN** install.sh checks the last-alive timer and finds no next run scheduled
- **THEN** it prints the same kind of warning it already prints for the heartbeat timer, naming the commands to inspect it, without failing the rest of the install

## MODIFIED Requirements

### Requirement: Uninstall script reverses installation
Run as root, the uninstall script SHALL:
- disable, stop and remove the boot notification
- stop, disable and remove the shutdown notification without sending a message
- stop, disable and remove the heartbeat timer and service
- stop, disable and remove the last-alive timer and service
- remove the login hook, restoring the system login configuration
- clear any failed state of HostWatch units
- remove the installed program files; remove `/var/lib/hostwatch` other than the boot-session ledger, which it SHALL ask the administrator about (see the dedicated requirement below)

It SHALL keep `/etc/hostwatch/` unless asked to purge it. It SHALL do this even when some of the installed files are already missing.

#### Scenario: Uninstall
- **WHEN** `sudo ./uninstall.sh` is run
- **THEN** no shutdown message is sent during the uninstall, no further boot, shutdown, heartbeat or login messages are sent, no hostwatch units, failed units or login entries remain, the configuration directory is kept, and `/var/lib/hostwatch` is gone except for the ledger per the ledger requirement below

#### Scenario: Purge
- **WHEN** `sudo ./uninstall.sh --purge` is run
- **THEN** `/etc/hostwatch/` is also removed

#### Scenario: Uninstall shortly after boot
- **WHEN** `sudo ./uninstall.sh` is run while the boot notification is still retrying
- **THEN** the boot notification is stopped and sends nothing afterwards

#### Scenario: Unit file already deleted
- **WHEN** `/etc/systemd/system/hostwatch-boot.service` was deleted by hand before `sudo ./uninstall.sh` is run
- **THEN** no enablement link for it remains after the uninstall

#### Scenario: Uninstall removes the last-alive timer
- **WHEN** `sudo ./uninstall.sh` is run
- **THEN** no hostwatch-last-alive timer or service, enabled or failed, remains afterward

## ADDED Requirements

### Requirement: Uninstall asks before removing the boot-session ledger
The uninstall script SHALL ask the administrator whether to remove the boot-session ledger (the uptime-summary ledger under `/var/lib/hostwatch/`), defaulting to keeping it when run without a terminal or when declined.

#### Scenario: Ledger kept by default
- **WHEN** `sudo ./uninstall.sh` is run non-interactively (no terminal)
- **THEN** the boot-session ledger is kept

#### Scenario: Ledger removed on request
- **WHEN** `sudo ./uninstall.sh` is run interactively and the administrator agrees to remove the ledger
- **THEN** the boot-session ledger is deleted
