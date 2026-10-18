# Spec Delta

## MODIFIED Requirements

### Requirement: Reinstall preserves existing configuration
Running the install script again SHALL update the program files. It SHALL NOT change an existing configuration file unless the administrator asks for a new webhook, and it SHALL never lose the configured webhook. Re-running the install script with the same answers SHALL leave the configuration file byte-for-byte unchanged.

#### Scenario: Upgrade
- **WHEN** the install script is run on a host where the configuration already holds a real webhook
- **THEN** the program files are updated and the configuration is unchanged

#### Scenario: Repeated re-runs
- **WHEN** `sudo ./install.sh --yes` is run three times in a row on an installed host
- **THEN** `/etc/hostwatch/config.ini` has the same content, owner `root:root` and mode `600` after each run

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

## ADDED Requirements

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
