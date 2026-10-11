# Spec Delta

## MODIFIED Requirements

### Requirement: Login message content
The login message SHALL carry the common identification defined by message-identity, with the event `Login: <username>`. Its own fields SHALL be the username, the login type (Graphical, TTY or SSH) and the date and time in the configured display format. For SSH logins it SHALL also include the remote IP address. For TTY logins it SHALL include the terminal name.

#### Scenario: SSH message content
- **WHEN** user `alice` logs in over SSH from `203.0.113.7` to host `my-pc`
- **THEN** the header reads `🖥️ my-pc · Login: alice`, the fallback starts with `my-pc · `, and the message shows user `alice`, type "SSH", remote IP `203.0.113.7`, the login time, the local addresses and the logged-in users
