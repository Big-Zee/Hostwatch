# Spec Delta

## MODIFIED Requirements

### Requirement: Install script sets up the service
Run as root from the repository, the install script SHALL:
- copy the program files to system locations
- create `/etc/hostwatch/config.ini` from `config.example.ini` with mode `600`
- enable the boot, shutdown and heartbeat notifications
- enable the login hook system-wide

It SHALL refuse to run without root privileges.

#### Scenario: Fresh install
- **WHEN** `sudo ./install.sh` is run on a fresh Ubuntu 24.04 host
- **THEN** the boot and shutdown notifications are enabled, the heartbeat timer is enabled and active, the login hook is active, and the configuration file exists with mode `600`

#### Scenario: Not root
- **WHEN** `./install.sh` is run without root privileges
- **THEN** it exits with an error and changes nothing

### Requirement: Uninstall script reverses installation
Run as root, the uninstall script SHALL:
- disable and remove the boot notification
- stop, disable and remove the shutdown notification without sending a message
- stop, disable and remove the heartbeat timer and service
- remove the login hook, restoring the system login configuration
- remove the installed program files and `/var/lib/hostwatch`

It SHALL keep `/etc/hostwatch/` unless asked to purge it.

#### Scenario: Uninstall
- **WHEN** `sudo ./uninstall.sh` is run
- **THEN** no shutdown message is sent during the uninstall, no further boot, shutdown, heartbeat or login messages are sent, no hostwatch units or login entries remain, `/var/lib/hostwatch` is gone, and the configuration directory is kept

#### Scenario: Purge
- **WHEN** `sudo ./uninstall.sh --purge` is run
- **THEN** `/etc/hostwatch/` is also removed

## ADDED Requirements

### Requirement: Install applies the heartbeat interval
The install script SHALL read the heartbeat interval from the configuration and apply it to the heartbeat timer. Changing the interval SHALL take effect when the install script is run again. Re-running the install script SHALL NOT send a heartbeat or any other message by itself.

#### Scenario: Interval changed
- **WHEN** `interval_minutes` is changed from 60 to 15 and `sudo ./install.sh` is run again
- **THEN** the heartbeat timer fires every 15 minutes

#### Scenario: Re-run sends nothing
- **WHEN** `sudo ./install.sh` is run again on an installed host whose uptime is shorter than one interval
- **THEN** no Slack message is sent as a result of the install
