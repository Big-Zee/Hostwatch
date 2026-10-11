# Spec Delta

## Purpose

Defines where HostWatch reads its settings, which settings exist with their defaults, and how the configuration file holding the webhook secret is protected.

## ADDED Requirements

### Requirement: Configuration file location
The service SHALL read its settings from `/etc/hostwatch/config.ini` in INI format. For testing, an alternative path MAY be given explicitly on the command line or through an environment variable.

#### Scenario: Default location
- **WHEN** the service runs without an explicit config path
- **THEN** it reads `/etc/hostwatch/config.ini`

#### Scenario: Explicit path
- **WHEN** an alternative config path is supplied
- **THEN** the service reads settings from that path instead

### Requirement: Supported settings
The configuration SHALL support these settings: Slack webhook URL (required); public IP lookup enabled (default on); public IP service URL (default `https://api.ipify.org`); interface name prefixes to skip (default covers docker, bridge, veth, libvirt, LXC/LXD, tun/tap and VPN overlays); include IPv6 addresses (default off); and display timezone (default `local`, or an IANA zone name).

#### Scenario: Only the webhook is set
- **WHEN** the config file contains only a valid webhook URL
- **THEN** every other setting takes its documented default

#### Scenario: Timezone override
- **WHEN** the display timezone is set to `Europe/Warsaw`
- **THEN** all message timestamps are shown in that zone with its abbreviation (for example `CEST`)

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
