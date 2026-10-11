# slack-delivery Specification

## Purpose

Defines how HostWatch delivers messages to a Slack channel: message layout, retry behavior, failure logging and protection of the webhook secret.

## Requirements

### Requirement: Messages are delivered through the Slack incoming webhook
Each notification SHALL be sent as one HTTPS POST of a JSON payload to the configured Slack incoming webhook URL. The service SHALL NOT depend on any software beyond the Python 3 standard library and stock Ubuntu tools.

#### Scenario: Successful delivery
- **WHEN** a notification is sent and Slack answers with HTTP 200
- **THEN** exactly one message appears in the channel and no retry is made

### Requirement: Messages are readable on mobile
Each message SHALL use Slack Block Kit in the shared format defined by message-identity: a header starting with the machine, then labelled fields with one value per field. It SHALL also include a plain-text `text` fallback that starts with the machine label and summarizes the event, for push notifications and clients that cannot render blocks.

#### Scenario: Push notification preview
- **WHEN** a boot message from `my-pc` arrives on a phone
- **THEN** the push notification preview shows a readable one-line summary such as "my-pc · Booted at 2026-10-11 12:01:33 CEST"

### Requirement: Transient failures are retried with backoff
When sending fails because of a network error, a timeout, HTTP 429 or HTTP 5xx, the service SHALL retry boot and login notifications with increasing delays, up to a bounded number of attempts. Shutdown and heartbeat notifications SHALL make a single attempt with no retry. Every request SHALL have a timeout. Any other HTTP 4xx response SHALL NOT be retried.

#### Scenario: Network comes up late
- **WHEN** the first attempts fail because DNS or the network is not ready, and a later attempt succeeds
- **THEN** exactly one message is delivered

#### Scenario: Webhook revoked
- **WHEN** Slack answers HTTP 404 or 403
- **THEN** the service stops at once, without retrying, and logs the failure

#### Scenario: Shutdown delivery fails
- **WHEN** the single shutdown delivery attempt fails
- **THEN** no further attempt is made and the failure is logged

#### Scenario: Heartbeat delivery fails
- **WHEN** the single heartbeat delivery attempt fails
- **THEN** no further attempt is made, the failure is logged and the heartbeat is dropped

### Requirement: Final failures are logged to the journal
When delivery gives up, the service SHALL write an error entry to the systemd journal. The entry SHALL give the event type and the reason for the final failure. The service SHALL then exit without signalling a failure that would mark boot or login as failed.

#### Scenario: Slack unreachable
- **WHEN** all attempts fail
- **THEN** `journalctl -t hostwatch` shows an error naming the event and the last error

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

### Requirement: Test and dry-run modes
The service SHALL provide a command that sends a sample test message using the installed configuration. The test message SHALL carry the full common identification, so it shows exactly how this machine appears in the channel. The service SHALL also provide a dry-run option for any event that prints the payload that would be sent, without sending it.

#### Scenario: Test after install
- **WHEN** the administrator runs the test command with a valid configuration
- **THEN** one test message appears in the channel, showing the machine label, local addresses and logged-in users

#### Scenario: Dry run
- **WHEN** a boot event is run in dry-run mode
- **THEN** the JSON payload is printed and nothing is sent to Slack
