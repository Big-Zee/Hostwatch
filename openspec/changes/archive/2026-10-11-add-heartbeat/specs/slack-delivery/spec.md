# Spec Delta

## MODIFIED Requirements

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
