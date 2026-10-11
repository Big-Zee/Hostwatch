# Spec Delta

## MODIFIED Requirements

### Requirement: Messages are readable on mobile
Each message SHALL use Slack Block Kit in the shared format defined by message-identity: a header starting with the machine, then labelled fields with one value per field. It SHALL also include a plain-text `text` fallback that starts with the machine label and summarizes the event, for push notifications and clients that cannot render blocks.

#### Scenario: Push notification preview
- **WHEN** a boot message from `my-pc` arrives on a phone
- **THEN** the push notification preview shows a readable one-line summary such as "my-pc · Booted at 2026-10-11 12:01:33 CEST"

### Requirement: Test and dry-run modes
The service SHALL provide a command that sends a sample test message using the installed configuration. The test message SHALL carry the full common identification, so it shows exactly how this machine appears in the channel. The service SHALL also provide a dry-run option for any event that prints the payload that would be sent, without sending it.

#### Scenario: Test after install
- **WHEN** the administrator runs the test command with a valid configuration
- **THEN** one test message appears in the channel, showing the machine label, local addresses and logged-in users

#### Scenario: Dry run
- **WHEN** a boot event is run in dry-run mode
- **THEN** the JSON payload is printed and nothing is sent to Slack
