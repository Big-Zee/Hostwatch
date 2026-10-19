# Spec Delta

## ADDED Requirements

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
