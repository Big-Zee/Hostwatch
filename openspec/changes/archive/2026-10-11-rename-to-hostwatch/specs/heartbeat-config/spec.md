# Spec Delta

## REMOVED Requirements

### Requirement: Configuration file location
**Reason**: Capability renamed to `hostwatch-config` as part of the project rename; the config moves to `/etc/hostwatch/config.ini`.
**Migration**: See `hostwatch-config` – "Configuration file location". No host has the old version installed, so there is nothing to migrate.

### Requirement: Supported settings
**Reason**: Capability renamed to `hostwatch-config`; the settings are unchanged.
**Migration**: See `hostwatch-config` – "Supported settings".

### Requirement: Invalid or missing configuration is reported, not fatal to the host
**Reason**: Capability renamed to `hostwatch-config`; the behavior is unchanged.
**Migration**: See `hostwatch-config` – "Invalid or missing configuration is reported, not fatal to the host".

### Requirement: Configuration file is root-only
**Reason**: Capability renamed to `hostwatch-config`; the behavior is unchanged.
**Migration**: See `hostwatch-config` – "Configuration file is root-only".
