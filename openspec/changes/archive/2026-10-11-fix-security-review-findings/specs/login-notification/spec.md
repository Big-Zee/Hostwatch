# Spec Delta

## MODIFIED Requirements

### Requirement: Login is never delayed or blocked
Sending the login notification SHALL NOT noticeably delay the login, and any failure SHALL NOT prevent it. This includes a missing configuration, no network, Slack errors or a crash of the notifier. Delivery SHALL happen in the background, and final failures SHALL be logged to the journal. The background delivery for one login SHALL end within 60 seconds, whatever the state of the network or Slack.

#### Scenario: Offline SSH login
- **WHEN** a user logs in while Slack is unreachable
- **THEN** the login completes normally without waiting for delivery, and the failure is logged to the journal

#### Scenario: Notifier missing or broken
- **WHEN** the notifier program is removed or fails while the login hook is still configured
- **THEN** users can still log in

#### Scenario: DNS hangs during delivery
- **WHEN** a user logs in while name resolution hangs
- **THEN** the login completes normally and the background HostWatch process for that login is gone within 60 seconds

## ADDED Requirements

### Requirement: Login hook reads only the installed configuration
When run as the login hook, the service SHALL read `/etc/hostwatch/config.ini` and SHALL ignore the configuration-path environment variable, because the hook runs as root with an environment assembled by PAM. An explicit `--config` option and dry runs SHALL keep working for testing.

#### Scenario: Environment override in the PAM environment
- **WHEN** the PAM environment of a login contains `HOSTWATCH_CONFIG` pointing to another file
- **THEN** the login notification uses `/etc/hostwatch/config.ini` and the other file is not read

#### Scenario: Dry run from a shell
- **WHEN** an administrator runs `HOSTWATCH_CONFIG=./test.ini PAM_TYPE=open_session PAM_SERVICE=sshd PAM_USER=alice hostwatch login --dry-run`
- **THEN** the settings from `./test.ini` are used for the printed payload
