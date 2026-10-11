# Spec Delta

## MODIFIED Requirements

### Requirement: Install script sets up the service
Run as root from the repository, the install script SHALL:
- copy the program files to system locations
- create `/etc/hostwatch/config.ini` from `config.example.ini` with mode `600`
- enable the boot and shutdown notifications
- enable the login hook system-wide

It SHALL refuse to run without root privileges.

#### Scenario: Fresh install
- **WHEN** `sudo ./install.sh` is run on a fresh Ubuntu 24.04 host
- **THEN** the boot and shutdown notifications are enabled, the login hook is active, and the configuration file exists with mode `600`

#### Scenario: Not root
- **WHEN** `./install.sh` is run without root privileges
- **THEN** it exits with an error and changes nothing

### Requirement: Uninstall script reverses installation
Run as root, the uninstall script SHALL:
- disable and remove the boot notification
- stop, disable and remove the shutdown notification without sending a message
- remove the login hook, restoring the system login configuration
- remove the installed program files and `/var/lib/hostwatch`

It SHALL keep `/etc/hostwatch/` unless asked to purge it.

#### Scenario: Uninstall
- **WHEN** `sudo ./uninstall.sh` is run
- **THEN** no shutdown message is sent during the uninstall, no further boot, shutdown or login messages are sent, no hostwatch entries remain in the system login configuration, `/var/lib/hostwatch` is gone, and the configuration directory is kept

#### Scenario: Purge
- **WHEN** `sudo ./uninstall.sh --purge` is run
- **THEN** `/etc/hostwatch/` is also removed

## ADDED Requirements

### Requirement: Install arms shutdown handling without a false warning
The install script SHALL start the shutdown notification at once, so the first shutdown after install is announced without a reboot. It SHALL create `/var/lib/hostwatch` and record a clean state, so the first boot after install shows no unclean-shutdown warning.

#### Scenario: Active right after install
- **WHEN** `sudo ./install.sh` has finished
- **THEN** the shutdown notification is active and `/var/lib/hostwatch` exists

#### Scenario: First boot after install
- **WHEN** the host is rebooted for the first time after install
- **THEN** the boot message contains no unclean-shutdown warning
