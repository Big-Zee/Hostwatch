# Spec Delta

## MODIFIED Requirements

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
