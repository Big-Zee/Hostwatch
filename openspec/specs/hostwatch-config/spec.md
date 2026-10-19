# hostwatch-config Specification

## Purpose

Defines where HostWatch reads its settings, which settings exist with their defaults, and how the configuration file holding the webhook secret is protected.

## Requirements

### Requirement: Configuration file location
The service SHALL read its settings from `/etc/hostwatch/config.ini` in INI format. For testing, an alternative path MAY be given explicitly on the command line or through an environment variable.

#### Scenario: Default location
- **WHEN** the service runs without an explicit config path
- **THEN** it reads `/etc/hostwatch/config.ini`

#### Scenario: Explicit path
- **WHEN** an alternative config path is supplied
- **THEN** the service reads settings from that path instead

### Requirement: Supported settings
The configuration SHALL support these settings: Slack webhook URL (required); friendly machine name (optional, unset by default); interface name prefixes to skip (default covers docker, bridge, veth, libvirt, LXC/LXD, tun/tap and VPN overlays); include IPv6 addresses (default off); display timezone (default `local`, or an IANA zone name); heartbeat enabled (default on); and heartbeat interval in minutes (default 60).

#### Scenario: Only the webhook is set
- **WHEN** the config file contains only a valid webhook URL
- **THEN** every other setting takes its documented default, messages label the machine by hostname alone, and heartbeats are sent every 60 minutes

#### Scenario: Timezone override
- **WHEN** the display timezone is set to `Europe/Warsaw`
- **THEN** all message timestamps are shown in that zone with its abbreviation (for example `CEST`)

#### Scenario: Machine name set
- **WHEN** `machine_name = Office PC` is set under `[display]`
- **THEN** messages label the machine `Office PC (<hostname>)`

### Requirement: Invalid or missing configuration is reported, not fatal to the host
When the config file is missing or unreadable, is not valid UTF-8, the webhook URL is missing, still the placeholder, not an `https://` URL, or contains whitespace or control characters, or the timezone is unknown, the service SHALL log a clear error to the systemd journal and exit without sending. The error SHALL NOT contain the webhook URL. It SHALL NOT affect boot or login.

#### Scenario: Placeholder webhook
- **WHEN** the webhook URL still holds the placeholder from `config.example.ini`
- **THEN** no request is sent to Slack and the journal records that the webhook is not configured

#### Scenario: Unknown timezone
- **WHEN** the display timezone names a zone that does not exist
- **THEN** the journal records the invalid timezone and no message is sent

#### Scenario: Inline comment after the webhook
- **WHEN** the config contains `webhook_url = https://hooks.slack.com/services/T0/B0/XYZ # prod`
- **THEN** the journal records that the webhook URL is invalid, the entry contains no part of the URL, and no request is sent

#### Scenario: Config saved with a byte-order mark
- **WHEN** the config file is valid UTF-8 that starts with a byte-order mark, as some Windows editors write it
- **THEN** it is read normally and notifications are sent

#### Scenario: Config that is not UTF-8
- **WHEN** the config file contains bytes that are not valid UTF-8, for example a Latin-1 `machine_name`
- **THEN** the journal records a configuration error, nothing is sent, and the boot unit does not fail

### Requirement: Configuration file is root-only
The installed configuration file SHALL be owned by root with permissions `600`, because it contains the webhook secret. Every run of the install script SHALL restore this ownership and mode on an existing file, without changing its content.

#### Scenario: Permissions after install
- **WHEN** installation creates the configuration file
- **THEN** the file is owned by `root:root` with mode `600`

#### Scenario: Readable config repaired on re-install
- **WHEN** an administrator created `/etc/hostwatch/config.ini` with mode `644` and runs the install script
- **THEN** the file is `root:root` with mode `600` afterwards, its content is unchanged, and the script says it corrected the permissions

### Requirement: Unsupported settings are ignored
Settings that the service does not support, including settings dropped from earlier versions, SHALL be ignored silently whatever their value. They SHALL NOT cause an error, a warning or a failed notification.

#### Scenario: Config from an earlier version
- **WHEN** the config file still contains a setting that earlier versions supported, with any value, even one that is not valid for its old type
- **THEN** the config loads without error, nothing about it is logged, and notifications are sent normally

### Requirement: Heartbeat interval is validated
The heartbeat interval SHALL be a whole number of minutes from 5 to 1440. An invalid value SHALL be reported as a configuration error that names the setting. It SHALL NOT be silently replaced.

#### Scenario: Interval too short
- **WHEN** `interval_minutes = 1` is set and `install.sh` is run
- **THEN** the installer stops with an error naming `interval_minutes` and its allowed range

#### Scenario: Not a number
- **WHEN** `interval_minutes = hourly` is set
- **THEN** a heartbeat run logs a configuration error naming `interval_minutes` and sends nothing

### Requirement: Daily uptime summary settings
The configuration SHALL support a `[uptime]` section with: `daily_summary_enabled` (whether boot, shutdown and heartbeat messages show an "Uptime today" field; default on), `last_alive_interval_minutes` (how often the last-alive timestamp is refreshed by its timer; default 5), and `retention_days` (how long ledger entries are kept; default 90). Settings not present in the config file SHALL take these defaults.

#### Scenario: Defaults when unset
- **WHEN** the config file has no `[uptime]` section
- **THEN** the daily summary is shown, the last-alive timer runs every 5 minutes, and ledger entries are kept for 90 days

#### Scenario: Daily summary disabled
- **WHEN** `daily_summary_enabled = false` is set under `[uptime]`
- **THEN** boot, shutdown and heartbeat messages omit the "Uptime today" field, and the ledger and last-alive timer keep running

### Requirement: Uptime settings are validated
`last_alive_interval_minutes` SHALL be a whole number of minutes from 1 to 60. `retention_days` SHALL be a whole number of days of at least 1. An invalid value for either SHALL be reported as a configuration error that names the setting, without silently replacing it; `daily_summary_enabled` not matching a recognized boolean value SHALL be reported the same way.

#### Scenario: Interval not a number
- **WHEN** `last_alive_interval_minutes = often` is set
- **THEN** install.sh and the affected runs report a configuration error naming `last_alive_interval_minutes`, without changing it

#### Scenario: Retention out of range
- **WHEN** `retention_days = 0` is set
- **THEN** a configuration error names `retention_days` and its allowed range
