# login-notification Specification

## Purpose

Announces in Slack every interactive user login on the host (graphical, TTY or SSH), exactly once per session, without ever delaying or blocking the login.

## Requirements

### Requirement: One notification per interactive login session
The service SHALL send exactly one login notification when an interactive session is opened through a graphical display manager, a text console (TTY) or SSH. Every new session SHALL be announced, even when the same user already has other sessions open.

#### Scenario: Desktop login
- **WHEN** a user logs in at the graphical login screen
- **THEN** exactly one login message with login type "Graphical" appears

#### Scenario: SSH login while desktop session is open
- **WHEN** the same user, already logged in on the desktop, opens an SSH session
- **THEN** exactly one additional login message with login type "SSH" appears

#### Scenario: TTY login
- **WHEN** a user logs in on a text console
- **THEN** exactly one login message with login type "TTY" appears

### Requirement: Non-interactive and privilege-change sessions are ignored
The service SHALL NOT send notifications for `su`, `sudo`, cron jobs, the display manager's own greeter session, the per-user service manager, session close events or other non-login services.

#### Scenario: sudo
- **WHEN** a logged-in user runs `sudo -i`
- **THEN** no login message is sent

#### Scenario: Logout
- **WHEN** a user logs out
- **THEN** no message is sent

### Requirement: Login message content
The login message SHALL carry the common identification defined by message-identity, with the event `Login: <username>`. Its own fields SHALL be the username, the login type (Graphical, TTY or SSH) and the date and time in the configured display format. For SSH logins it SHALL also include the remote IP address. For TTY logins it SHALL include the terminal name.

#### Scenario: SSH message content
- **WHEN** user `alice` logs in over SSH from `203.0.113.7` to host `my-pc`
- **THEN** the header reads `🖥️ my-pc · Login: alice`, the fallback starts with `my-pc · `, and the message shows user `alice`, type "SSH", remote IP `203.0.113.7`, the login time, the local addresses and the logged-in users

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

### Requirement: Login hook reads only the installed configuration
When run as the login hook, the service SHALL read `/etc/hostwatch/config.ini` and SHALL ignore the configuration-path environment variable, because the hook runs as root with an environment assembled by PAM. An explicit `--config` option and dry runs SHALL keep working for testing.

#### Scenario: Environment override in the PAM environment
- **WHEN** the PAM environment of a login contains `HOSTWATCH_CONFIG` pointing to another file
- **THEN** the login notification uses `/etc/hostwatch/config.ini` and the other file is not read

#### Scenario: Dry run from a shell
- **WHEN** an administrator runs `HOSTWATCH_CONFIG=./test.ini PAM_TYPE=open_session PAM_SERVICE=sshd PAM_USER=alice hostwatch login --dry-run`
- **THEN** the settings from `./test.ini` are used for the printed payload
