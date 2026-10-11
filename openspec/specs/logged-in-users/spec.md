# logged-in-users Specification

## Purpose

Defines which users HostWatch reports as logged in, how their sessions are classified, deduplicated and filtered, and what is shown when nobody is logged in.

## Requirements

### Requirement: Users are listed per session with their type
The users list SHALL contain one entry per interactive user session. Each entry SHALL have the username and the session type: `desktop` for graphical sessions, `ssh` for remote logins, or `tty` for local text consoles. SSH entries SHALL include the remote IP address.

#### Scenario: Desktop and SSH sessions
- **WHEN** `alice` has a desktop session open and `alice` is also logged in over SSH from `203.0.113.7`
- **THEN** the list shows two entries: `alice` as desktop, and `alice` as ssh from `203.0.113.7`

#### Scenario: Text console
- **WHEN** `bob` is logged in on a text console
- **THEN** the list shows `bob` as tty

### Requirement: Sessions are deduplicated
Terminals opened inside one desktop session SHALL NOT add entries, so one desktop session appears once. Sessions that are identical in username, type and remote address SHALL be shown once, with the number of sessions.

#### Scenario: Many terminals in one desktop
- **WHEN** `alice` has one desktop session with five terminal windows open
- **THEN** the list shows `alice` as desktop once

#### Scenario: Two SSH sessions from the same address
- **WHEN** `alice` has two SSH sessions from `203.0.113.7`
- **THEN** the list shows one ssh entry for `alice` from `203.0.113.7`, marked as 2 sessions

### Requirement: System and display-manager sessions are excluded
The list SHALL leave out:
- login-screen (greeter) and lock-screen sessions
- background and service sessions (for example from `su` or cron)
- sessions that are closing
- display-manager and system accounts such as `gdm`, `gdm-greeter`, `lightdm` and `sddm`

#### Scenario: Login screen showing
- **WHEN** the machine sits at the graphical login screen and nobody has logged in
- **THEN** the greeter's account does not appear in the list

### Requirement: Empty list is stated explicitly
When no user session qualifies, the users field SHALL read "No users logged in".

#### Scenario: Boot without auto-login
- **WHEN** a machine with auto-login disabled boots
- **THEN** the boot message's users field reads "No users logged in"

### Requirement: Session data source and fallback
Sessions SHALL be read from systemd-logind. When logind cannot be queried, the service SHALL fall back to the login records (`who`), applying the same classification and deduplication as far as that data allows. If neither source is available, the field SHALL read "No users logged in" and the message SHALL still be sent.

#### Scenario: logind unavailable
- **WHEN** `loginctl` fails or is missing but `who` lists `bob` on `pts/0` from `203.0.113.9`
- **THEN** the list shows `bob` as ssh from `203.0.113.9`

#### Scenario: No source available
- **WHEN** neither `loginctl` nor `who` can be run
- **THEN** the users field reads "No users logged in" and the message is sent
