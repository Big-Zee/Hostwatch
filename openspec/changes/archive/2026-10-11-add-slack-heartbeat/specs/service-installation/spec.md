# Spec Delta

## Purpose

Defines how an administrator installs, configures and completely removes slack-heartbeat on an Ubuntu host using the provided scripts.

## ADDED Requirements

### Requirement: Install script sets up the service
Run as root from the repository, the install script SHALL:
- copy the program files to system locations
- create `/etc/slack-heartbeat/config.ini` from `config.example.ini` with mode `600`
- enable the boot notification so it runs on every boot
- enable the login hook system-wide

It SHALL refuse to run without root privileges.

#### Scenario: Fresh install
- **WHEN** `sudo ./install.sh` is run on a fresh Ubuntu 24.04 host
- **THEN** the boot notification is enabled, the login hook is active, and the configuration file exists with mode `600`

#### Scenario: Not root
- **WHEN** `./install.sh` is run without root privileges
- **THEN** it exits with an error and changes nothing

### Requirement: Install supplies the webhook without committing it
The install script SHALL accept the webhook URL from an environment variable, or ask for it interactively when run on a terminal, and write it into the installed configuration file. If neither is given, the placeholder SHALL be kept and the script SHALL tell the administrator to edit the file.

#### Scenario: Webhook from environment
- **WHEN** `sudo SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... ./install.sh` is run
- **THEN** the installed configuration contains that webhook URL and nothing in the repository changes

### Requirement: Reinstall preserves existing configuration
Running the install script again SHALL update the program files. It SHALL NOT overwrite an existing configuration file.

#### Scenario: Upgrade
- **WHEN** the install script is run on a host where the configuration already holds a real webhook
- **THEN** the program files are updated and the configuration is unchanged

### Requirement: Uninstall script reverses installation
Run as root, the uninstall script SHALL:
- disable and remove the boot notification
- remove the login hook, restoring the system login configuration
- remove the installed program files

It SHALL keep `/etc/slack-heartbeat/` unless asked to purge it.

#### Scenario: Uninstall
- **WHEN** `sudo ./uninstall.sh` is run
- **THEN** no further boot or login messages are sent, no slack-heartbeat entries remain in the system login configuration, and the configuration directory is kept

#### Scenario: Purge
- **WHEN** `sudo ./uninstall.sh --purge` is run
- **THEN** `/etc/slack-heartbeat/` is also removed
