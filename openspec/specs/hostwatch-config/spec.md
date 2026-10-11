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
When the config file is missing or unreadable, the webhook URL is missing, still the placeholder, or not an `https://` URL, or the timezone is unknown, the service SHALL log a clear error to the systemd journal and exit without sending. It SHALL NOT affect boot or login.

#### Scenario: Placeholder webhook
- **WHEN** the webhook URL still holds the placeholder from `config.example.ini`
- **THEN** no request is sent to Slack and the journal records that the webhook is not configured

#### Scenario: Unknown timezone
- **WHEN** the display timezone names a zone that does not exist
- **THEN** the journal records the invalid timezone and no message is sent

### Requirement: Configuration file is root-only
The installed configuration file SHALL be owned by root with permissions `600`, because it contains the webhook secret.

#### Scenario: Permissions after install
- **WHEN** installation creates the configuration file
- **THEN** the file is owned by `root:root` with mode `600`

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
