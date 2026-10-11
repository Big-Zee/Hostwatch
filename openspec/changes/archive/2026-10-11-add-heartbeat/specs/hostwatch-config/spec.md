# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Heartbeat interval is validated
The heartbeat interval SHALL be a whole number of minutes from 5 to 1440. An invalid value SHALL be reported as a configuration error that names the setting. It SHALL NOT be silently replaced.

#### Scenario: Interval too short
- **WHEN** `interval_minutes = 1` is set and `install.sh` is run
- **THEN** the installer stops with an error naming `interval_minutes` and its allowed range

#### Scenario: Not a number
- **WHEN** `interval_minutes = hourly` is set
- **THEN** a heartbeat run logs a configuration error naming `interval_minutes` and sends nothing
