# Spec Delta

## MODIFIED Requirements

### Requirement: One notification per boot after the network is up
The service SHALL send exactly one boot notification per boot. It SHALL send it after the system reports the network online. Switching the system between targets while it runs SHALL NOT send another boot notification.

#### Scenario: Normal boot
- **WHEN** the PC boots and the network comes online
- **THEN** exactly one boot message appears in the Slack channel

#### Scenario: Switching targets while running
- **WHEN** an administrator runs `systemctl isolate multi-user.target`, `systemctl isolate graphical.target`, or isolates `rescue.target` and returns, without rebooting
- **THEN** no further boot message is sent, and the next boot message after a real reboot judges the previous shutdown correctly

### Requirement: Boot is never delayed or broken
The boot notification SHALL NOT delay the system reaching its normal boot target. In particular, HostWatch SHALL NOT make the boot target wait for the network to come online. Failure of the notification, including an unexpected error in HostWatch itself, SHALL NOT mark boot as degraded.

#### Scenario: Offline boot
- **WHEN** the PC boots with no network
- **THEN** boot completes in its usual time, the service retries in the background, then logs the failure to the journal, and no failed unit is reported

#### Scenario: Boot target not held back by network-online
- **WHEN** the host boots with its network cable unplugged and `systemd-analyze critical-chain multi-user.target` is inspected
- **THEN** no HostWatch unit appears in the chain and the target is not reached later because of HostWatch

#### Scenario: Unexpected error during boot notification
- **WHEN** the boot notification hits an unexpected error, such as undecodable command output
- **THEN** the error is logged to the journal without exception text, nothing is sent, and the boot unit does not end in the failed state
