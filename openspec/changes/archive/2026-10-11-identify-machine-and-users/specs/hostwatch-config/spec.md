# Spec Delta

## MODIFIED Requirements

### Requirement: Supported settings
The configuration SHALL support these settings: Slack webhook URL (required); friendly machine name (optional, unset by default); interface name prefixes to skip (default covers docker, bridge, veth, libvirt, LXC/LXD, tun/tap and VPN overlays); include IPv6 addresses (default off); and display timezone (default `local`, or an IANA zone name).

#### Scenario: Only the webhook is set
- **WHEN** the config file contains only a valid webhook URL
- **THEN** every other setting takes its documented default, and messages label the machine by hostname alone

#### Scenario: Timezone override
- **WHEN** the display timezone is set to `Europe/Warsaw`
- **THEN** all message timestamps are shown in that zone with its abbreviation (for example `CEST`)

#### Scenario: Machine name set
- **WHEN** `machine_name = Office PC` is set under `[display]`
- **THEN** messages label the machine `Office PC (<hostname>)`
