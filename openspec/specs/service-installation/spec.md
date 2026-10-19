# service-installation Specification

## Purpose

Defines how an administrator installs, configures and completely removes HostWatch on an Ubuntu host using the provided scripts.

## Requirements

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

### Requirement: Install supplies the webhook without committing it
The install script SHALL accept the webhook URL from an environment variable, or ask for it interactively when run on a terminal, and write it into the installed configuration file. If neither is given, the placeholder SHALL be kept and the script SHALL tell the administrator to edit the file. A webhook containing whitespace or control characters SHALL be refused, keeping the placeholder. The documentation SHALL NOT recommend placing the webhook on a command line, where shell history, process listings and sudo logs record it.

#### Scenario: Webhook from environment
- **WHEN** an administrator reads the URL with `read -rs SLACK_WEBHOOK_URL`, exports it, and runs `sudo --preserve-env=SLACK_WEBHOOK_URL ./install.sh`
- **THEN** the installed configuration contains that webhook URL, nothing in the repository changes, and the URL does not appear in shell history or in any process's arguments

#### Scenario: Webhook with a trailing comment
- **WHEN** the supplied webhook is `https://hooks.slack.com/services/T0/B0/XYZ # prod`
- **THEN** the script says the webhook is invalid, without printing it, and keeps the placeholder

### Requirement: Reinstall preserves existing configuration
Running the install script again SHALL update the program files. It SHALL NOT change an existing configuration file unless the administrator asks for a new webhook, and it SHALL never lose the configured webhook. Re-running the install script with the same answers SHALL leave the configuration file byte-for-byte unchanged.

#### Scenario: Upgrade
- **WHEN** the install script is run on a host where the configuration already holds a real webhook
- **THEN** the program files are updated and the configuration is unchanged

#### Scenario: Repeated re-runs
- **WHEN** `sudo ./install.sh --yes` is run three times in a row on an installed host
- **THEN** `/etc/hostwatch/config.ini` has the same content, owner `root:root` and mode `600` after each run

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

### Requirement: Uninstall asks before removing the boot-session ledger
The uninstall script SHALL ask the administrator whether to remove the boot-session ledger (the uptime-summary ledger under `/var/lib/hostwatch/`), defaulting to keeping it when run without a terminal or when declined.

#### Scenario: Ledger kept by default
- **WHEN** `sudo ./uninstall.sh` is run non-interactively (no terminal)
- **THEN** the boot-session ledger is kept

#### Scenario: Ledger removed on request
- **WHEN** `sudo ./uninstall.sh` is run interactively and the administrator agrees to remove the ledger
- **THEN** the boot-session ledger is deleted

### Requirement: Install arms shutdown handling without a false warning
The install script SHALL start the shutdown notification at once, so the first shutdown after install is announced without a reboot. On first install it SHALL create `/var/lib/hostwatch` and record a clean state, so the first boot after install shows no unclean-shutdown warning. Re-running the install script SHALL NOT change the clean-shutdown record.

#### Scenario: Active right after install
- **WHEN** `sudo ./install.sh` has finished
- **THEN** the shutdown notification is active and `/var/lib/hostwatch` exists

#### Scenario: First boot after install
- **WHEN** the host is rebooted for the first time after install
- **THEN** the boot message contains no unclean-shutdown warning

#### Scenario: Crash after a re-install
- **WHEN** `sudo ./install.sh` is run again on an installed host and the host then loses power
- **THEN** the next boot message carries the unclean-shutdown warning

### Requirement: Install applies the heartbeat interval
The install script SHALL read the heartbeat interval from the configuration and apply it to the heartbeat timer. Changing the interval SHALL take effect when the install script is run again. Re-running the install script SHALL NOT send a heartbeat or any other message by itself, however long the host has been up.

#### Scenario: Interval changed
- **WHEN** `interval_minutes` is changed from 60 to 15 and `sudo ./install.sh` is run again
- **THEN** the heartbeat timer fires every 15 minutes

#### Scenario: Re-run sends nothing
- **WHEN** `sudo ./install.sh` is run again on an installed host whose uptime is shorter than one interval
- **THEN** no Slack message is sent as a result of the install

#### Scenario: Interval changed on a long-running host
- **WHEN** `interval_minutes` is changed and `sudo ./install.sh` is run on a host that has been up longer than the new interval
- **THEN** no heartbeat is sent as a result of the install, and the next one comes one new interval later

### Requirement: Install verifies the heartbeat schedule
After enabling the heartbeat timer, the install script SHALL check that systemd reports a monotonic trigger and a next run time for it. If either is missing, the script SHALL print a warning saying heartbeats will not be sent and how to inspect the timer. The warning SHALL NOT stop the rest of the installation.

#### Scenario: Timer scheduled
- **WHEN** `sudo ./install.sh` finishes on a host where the timer is scheduled
- **THEN** no heartbeat warning is printed and `systemctl list-timers hostwatch-heartbeat.timer` shows a NEXT time

#### Scenario: Timer not scheduled
- **WHEN** the heartbeat timer ends up with no next run time after `install.sh` enables it
- **THEN** the script prints a warning naming `hostwatch-heartbeat.timer` and the `systemctl list-timers` command to inspect it

### Requirement: Existing configuration is shown and confirmed
When `/etc/hostwatch/config.ini` exists and the script runs on a terminal, the install script SHALL NOT ask for the webhook. It SHALL show the masked webhook, the machine name and the heartbeat setting, then ask `Use this configuration? [Y/n]`. Y or an empty answer SHALL keep the file unchanged. N SHALL ask for a new webhook.

#### Scenario: Confirm the existing configuration
- **WHEN** `sudo ./install.sh` is run on a terminal on a host whose config holds a real webhook, `machine_name = Maja PC` and the default heartbeat, and the administrator presses Enter
- **THEN** the script shows the webhook masked, `Maja PC` and `enabled, every 60 min`, asks no other configuration question, and `/etc/hostwatch/config.ini` is byte-for-byte unchanged with owner `root:root` and mode `600`

#### Scenario: Replace the webhook
- **WHEN** the administrator answers `n` and enters a new valid webhook at the hidden prompt
- **THEN** the new webhook is written, every other setting in the file is kept, and the previous file is saved as `/etc/hostwatch/config.ini.bak`

#### Scenario: Answer n, then enter nothing
- **WHEN** the administrator answers `n` and leaves the new webhook empty
- **THEN** the configuration file is unchanged, no backup is written, and the installation continues

#### Scenario: Placeholder still in place
- **WHEN** the existing config still holds the placeholder webhook
- **THEN** the summary shows the webhook as not set, and keeping the configuration prints the note that `webhook_url` must be set

### Requirement: Installer options for unattended runs
The install script SHALL accept `--yes`, to keep an existing configuration without asking, and `--reconfigure`, to always ask for a new webhook. Without a terminal and without `--reconfigure`, it SHALL keep an existing configuration without asking. `SLACK_WEBHOOK_URL` SHALL replace an existing webhook only together with `--reconfigure`. Unknown or conflicting options SHALL stop the script before it changes anything.

#### Scenario: Unattended re-run
- **WHEN** `sudo ./install.sh --yes` is run on an installed host
- **THEN** no question is asked and the configuration file is unchanged

#### Scenario: No terminal
- **WHEN** `install.sh` is run as root from a script with no terminal on an installed host
- **THEN** no question is asked and the configuration file is unchanged

#### Scenario: Reconfigure from the environment
- **WHEN** `SLACK_WEBHOOK_URL` is exported and `sudo --preserve-env=SLACK_WEBHOOK_URL ./install.sh --reconfigure` is run with no terminal
- **THEN** the new webhook is written after the old file is saved as `config.ini.bak`, and no question is asked

#### Scenario: Reconfigure without a webhook source
- **WHEN** `install.sh --reconfigure` is run with no terminal and no `SLACK_WEBHOOK_URL`
- **THEN** the script exits with an error before changing anything

#### Scenario: Environment webhook without --reconfigure
- **WHEN** `SLACK_WEBHOOK_URL` is set and `install.sh` runs on a host that already has a configuration
- **THEN** the existing webhook is kept and the script says the variable was ignored and that `--reconfigure` replaces the webhook

#### Scenario: Conflicting options
- **WHEN** `sudo ./install.sh --yes --reconfigure` is run
- **THEN** the script exits with a usage error and changes nothing

### Requirement: Changed configuration is backed up first
Before the install script writes any change to an existing configuration file, it SHALL copy the current file to `/etc/hostwatch/config.ini.bak`, owned by `root:root` with mode `600`. The backup SHALL hold the previous content exactly.

#### Scenario: Backup before a new webhook
- **WHEN** the webhook of an existing configuration is replaced by the install script
- **THEN** `/etc/hostwatch/config.ini.bak` holds the previous file byte-for-byte, owned by `root:root` with mode `600`

### Requirement: Webhook entered at install is a Slack webhook
A webhook supplied to the install script, at the prompt or through `SLACK_WEBHOOK_URL`, SHALL start with `https://hooks.slack.com/` and SHALL NOT contain whitespace or control characters. Otherwise the script SHALL say it is invalid, without printing it, and keep the configuration as it was: the existing file, or the placeholder on a fresh install.

#### Scenario: Not a Slack webhook
- **WHEN** `https://example.com/hook` is entered at the webhook prompt
- **THEN** the script says the webhook must start with `https://hooks.slack.com/`, does not print the entered value, and the configuration is not changed

### Requirement: Install asks for a machine name on a fresh install
When the install script creates the configuration on a terminal, it SHALL ask for an optional machine name after the webhook and write a non-empty answer as `[display] machine_name`. An empty answer, or a run without a terminal, SHALL leave the machine name unset.

#### Scenario: Name given
- **WHEN** a fresh install on a terminal is answered with a webhook and the machine name `Maja PC`
- **THEN** `/etc/hostwatch/config.ini` contains `machine_name = Maja PC` under `[display]`

#### Scenario: Name left empty
- **WHEN** the machine name prompt is left empty
- **THEN** no `machine_name` is set and messages show the hostname alone

### Requirement: Installer never prints the webhook
The install script SHALL NOT write the full webhook URL, or any part of its path other than the last 4 characters, to the terminal, the systemd journal or any log. Wherever it shows the webhook, it SHALL show it masked as scheme and host followed by an ellipsis and the last 4 characters.

#### Scenario: Masked webhook in the summary
- **WHEN** the configured webhook is `https://hooks.slack.com/services/T000/B000/xyzabcd`
- **THEN** the installer shows `https://hooks.slack.com/…abcd`, and neither the installer output nor `journalctl` contains `T000`, `B000` or `xyzabcd`

### Requirement: Install reports settings missing from an existing configuration
When an existing configuration lacks a setting that this version supports, the install script SHALL keep the file as it is and list each missing setting with the default value that will be used.

#### Scenario: Config from an older version
- **WHEN** the existing config has no `[heartbeat]` section and the installer runs
- **THEN** the file is not changed and the output lists `[heartbeat] enabled` (default `true`) and `[heartbeat] interval_minutes` (default `60`) as missing

### Requirement: Installed command runs only installed code
The installed `hostwatch` command SHALL load its program code only from the installed program directory. Code found anywhere else on the host, including other directories under `/usr/local`, SHALL NOT be loaded by the installed command. Running the command from a repository checkout SHALL keep using that checkout's code.

#### Scenario: Unrelated directory under /usr/local/src
- **WHEN** a directory `/usr/local/src/hostwatch` exists, for example a clone of this repository
- **THEN** the installed command, the boot, shutdown and heartbeat units and the login hook still run the installed code and work normally

#### Scenario: Run from a checkout
- **WHEN** an administrator runs `bin/hostwatch test --dry-run --config config.example.ini` from a checkout
- **THEN** the checkout's code is used

### Requirement: Install and uninstall verify the login hook
After enabling the login hook, the install script SHALL check that the hook line is present in the system session configuration. If it is not, the script SHALL report the problem with the manual fix and exit with an error. After removing the login hook, the uninstall script SHALL check that the line is gone. If it is not, the script SHALL stop before removing the program, report the manual fix, and exit with an error.

#### Scenario: Hand-edited PAM configuration at install
- **WHEN** `/etc/pam.d/common-session` was edited by hand and `pam-auth-update` leaves it unchanged during `sudo ./install.sh`
- **THEN** the script exits with an error saying the login hook is not active and how to add it, instead of reporting success

#### Scenario: Hand-edited PAM configuration at uninstall
- **WHEN** the hook line is still in `/etc/pam.d/common-session` after `pam-auth-update --remove` during `sudo ./uninstall.sh`
- **THEN** the script exits with an error before deleting `/usr/local/bin/hostwatch`, so logins never point at a missing program, and it says how to remove the line
