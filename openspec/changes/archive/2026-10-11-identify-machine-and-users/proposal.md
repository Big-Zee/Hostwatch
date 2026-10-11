# Proposal

## Why

One Slack channel should be able to serve several PCs. Today each message names its host somewhere in the text, but nothing makes the machine stand out:
- the phone push preview may not start with it
- login messages lead with the user
- test messages lead with "HostWatch"

None of the messages say who is currently using the machine.

## What Changes

- **One shared message builder** makes every message type look the same. That covers boot, shutdown, login and test, and any future type such as a heartbeat.
- **Machine identification first:**
  - The header always starts with the machine, for example `🖥️ office-pc · Boot`.
  - The new optional setting `machine_name` (for example `Office PC`) shows as `Office PC (office-pc)`. Without it, only the hostname shows.
  - The plain-text fallback, used for phone push notifications and previews, always starts with the same machine label, for example `Office PC (office-pc) · Booted at …`.
- **Every message gets the local IP addresses,** using the existing rules and `interface: address` format. This now includes login and test messages.
- **Every message gets the logged-in users:**
  - Each entry has the username and session type (desktop, tty or ssh), plus the remote IP for ssh.
  - Data comes from systemd-logind (`loginctl`), with `who` as a fallback.
  - One desktop session counts once, however many terminals it has open. Separate sessions (desktop + SSH) are listed separately.
  - Greeter, display-manager and background sessions are left out.
  - With nobody logged in, the field says "No users logged in".
- **Header and fallback wording changes for every message type.** The old per-event headers (for example `:large_green_circle: my-pc is up`) are replaced by the shared format. The separate "Host" field is dropped, because the header carries the machine. Event-specific fields are unchanged: time, kernel boot time, uptime, user, type, remote IP, terminal.
- `config.example.ini` documents `machine_name`. The README gets a "Using HostWatch on several machines" section.

Out of scope:
- per-machine Slack channels
- a central dashboard
- a heartbeat message. The shared builder means a future heartbeat gets the same format automatically.

## Capabilities

### New Capabilities
- `message-identity`: The common parts of every message: the machine label in the header and at the start of the fallback, the optional friendly name, the local IP addresses and the logged-in users. All of them come from one builder.
- `logged-in-users`: Which users count as logged in, how sessions are classified, deduplicated and filtered, and what is shown when there are none.

### Modified Capabilities
- `boot-notification`: The boot message content is defined as the common identification plus its own fields.
- `shutdown-notification`: The shutdown message content is defined the same way. The event type moves into the header.
- `login-notification`: The login message content is defined the same way. Local IPs and logged-in users are now included.
- `slack-delivery`: The mobile-readability requirement uses the shared header and fallback. The test message carries the full identification.
- `hostwatch-config`: The supported settings include the optional `machine_name`.

## Impact

- **Code:**
  - `src/hostwatch/messages.py` is rewritten around one builder.
  - New `src/hostwatch/sessions.py` for logged-in users.
  - `config.py` gains `machine_name`.
  - `cli.py`: every command collects IPs and users, and the login payload is rebuilt on each attempt.
- **Tests:** messages and CLI tests updated, plus new session-parsing tests.
- **Docs:** `config.example.ini` and `README.md`.
- **Behavior:**
  - Message text changes for every type. Anyone who filters the channel by old header text has to adjust.
  - There is no network access beyond Slack, and no new dependencies: `loginctl` and `who` ship with Ubuntu.
