# Spec Delta

## MODIFIED Requirements

### Requirement: The webhook URL is never exposed
The webhook URL, or any part of it, SHALL NOT be written to logs, error messages or dry-run output. This SHALL hold for delivery failures caused by a malformed URL and for unexpected errors, whose log entries SHALL name the error type and location but not the error text. The repository SHALL contain only a placeholder webhook.

#### Scenario: Error log content
- **WHEN** a delivery failure is logged
- **THEN** the log entry does not contain the webhook URL

#### Scenario: Malformed URL reaches delivery
- **WHEN** delivery is attempted with a webhook URL that the HTTP client rejects as malformed
- **THEN** the log entry names the error type and contains no part of the URL's path

#### Scenario: Unexpected error
- **WHEN** an unexpected error occurs in a boot, login, shutdown or heartbeat run
- **THEN** the journal entry names the event, the error type and the code location, and contains no exception message

#### Scenario: Repository content
- **WHEN** the repository is inspected
- **THEN** `config.example.ini` contains only a placeholder webhook, and real `config.ini` files are git-ignored
