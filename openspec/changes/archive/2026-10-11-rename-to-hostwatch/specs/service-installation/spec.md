# Spec Delta

## MODIFIED Requirements

### Requirement: Install script sets up the service
Run as root from the repository, the install script SHALL:
- copy the program files to system locations
- create `/etc/hostwatch/config.ini` from `config.example.ini` with mode `600`
- enable the boot notification so it runs on every boot
- enable the login hook system-wide

It SHALL refuse to run without root privileges.

#### Scenario: Fresh install
- **WHEN** `sudo ./install.sh` is run on a fresh Ubuntu 24.04 host
- **THEN** the boot notification is enabled, the login hook is active, and the configuration file exists with mode `600`

#### Scenario: Not root
- **WHEN** `./install.sh` is run without root privileges
- **THEN** it exits with an error and changes nothing

### Requirement: Uninstall script reverses installation
Run as root, the uninstall script SHALL:
- disable and remove the boot notification
- remove the login hook, restoring the system login configuration
- remove the installed program files

It SHALL keep `/etc/hostwatch/` unless asked to purge it.

#### Scenario: Uninstall
- **WHEN** `sudo ./uninstall.sh` is run
- **THEN** no further boot or login messages are sent, no hostwatch entries remain in the system login configuration, and the configuration directory is kept

#### Scenario: Purge
- **WHEN** `sudo ./uninstall.sh --purge` is run
- **THEN** `/etc/hostwatch/` is also removed
