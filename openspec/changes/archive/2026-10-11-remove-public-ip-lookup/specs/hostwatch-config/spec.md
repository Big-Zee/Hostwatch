# Spec Delta

## MODIFIED Requirements

### Requirement: Supported settings
The configuration SHALL support these settings: Slack webhook URL (required); interface name prefixes to skip (default covers docker, bridge, veth, libvirt, LXC/LXD, tun/tap and VPN overlays); include IPv6 addresses (default off); and display timezone (default `local`, or an IANA zone name).

#### Scenario: Only the webhook is set
- **WHEN** the config file contains only a valid webhook URL
- **THEN** every other setting takes its documented default

#### Scenario: Timezone override
- **WHEN** the display timezone is set to `Europe/Warsaw`
- **THEN** all message timestamps are shown in that zone with its abbreviation (for example `CEST`)

## ADDED Requirements

### Requirement: Unsupported settings are ignored
Settings that the service does not support, including settings dropped from earlier versions, SHALL be ignored silently whatever their value. They SHALL NOT cause an error, a warning or a failed notification.

#### Scenario: Config from an earlier version
- **WHEN** the config file still contains a setting that earlier versions supported, with any value, even one that is not valid for its old type
- **THEN** the config loads without error, nothing about it is logged, and notifications are sent normally
