# Spec Delta

## Purpose

Announces in Slack every interactive user login on the host (graphical, TTY or SSH), exactly once per session, without ever delaying or blocking the login.

## ADDED Requirements

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
The login message SHALL contain the username, the login type (Graphical, TTY or SSH), the date and time in the configured display format, and the hostname. For SSH logins it SHALL also include the remote IP address. For TTY logins it SHALL include the terminal name.

#### Scenario: SSH message content
- **WHEN** user `alice` logs in over SSH from `203.0.113.7` to host `my-pc`
- **THEN** the message shows user `alice`, type "SSH", remote IP `203.0.113.7`, host `my-pc` and the login time

### Requirement: Login is never delayed or blocked
Sending the login notification SHALL NOT noticeably delay the login, and any failure SHALL NOT prevent it. This includes a missing configuration, no network, Slack errors or a crash of the notifier. Delivery SHALL happen in the background, and final failures SHALL be logged to the journal.

#### Scenario: Offline SSH login
- **WHEN** a user logs in while Slack is unreachable
- **THEN** the login completes normally without waiting for delivery, and the failure is logged to the journal

#### Scenario: Notifier missing or broken
- **WHEN** the notifier program is removed or fails while the login hook is still configured
- **THEN** users can still log in
