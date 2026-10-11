# Spec Delta

## MODIFIED Requirements

### Requirement: Final failures are logged to the journal
When delivery gives up, the service SHALL write an error entry to the systemd journal. The entry SHALL give the event type and the reason for the final failure. The service SHALL then exit without signalling a failure that would mark boot or login as failed.

#### Scenario: Slack unreachable
- **WHEN** all attempts fail
- **THEN** `journalctl -t hostwatch` shows an error naming the event and the last error
