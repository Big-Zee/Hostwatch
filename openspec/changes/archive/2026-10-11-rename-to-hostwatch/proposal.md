# Proposal

## Why

The repository and product are called HostWatch, but the service was built as `slack-heartbeat`. Later reports (uptime, top processes, shutdown) will make it a general host monitor rather than a Slack heartbeat. Using one name now prevents a confusing split between repository, binary, paths and journal tag. Nothing is installed anywhere yet, so the rename costs no migration.

## What Changes

**Naming:** "HostWatch" is the display name (README, Slack branding, docs) and `hostwatch` is the technical identifier (files, units, paths, journal tag).

- Command: `/usr/local/bin/slack-heartbeat` → `/usr/local/bin/hostwatch`.
- Library: `/usr/local/lib/slack-heartbeat/` → `/usr/local/lib/hostwatch/`.
- Python package: `src/slack_heartbeat/` → `src/hostwatch/`.
- Boot unit: `slack-heartbeat-boot.service` → `hostwatch-boot.service`, including `Description=`. The unit also sets `SyslogIdentifier=hostwatch`.
- Config: `/etc/slack-heartbeat/config.ini` → `/etc/hostwatch/config.ini`.
- Config path override variable: `SLACK_HEARTBEAT_CONFIG` → `HOSTWATCH_CONFIG`.
- PAM profile: pam-auth-update profile `slack-heartbeat` → `hostwatch`.
- Journal tag: `slack-heartbeat` → `hostwatch` (`journalctl -t hostwatch`).
- Slack branding: the message footer and the test-message header and fallback say "HostWatch". The HTTP User-Agent becomes `hostwatch`. Nothing else in the messages changes.
- `config.example.ini`, `install.sh`, `uninstall.sh`, README, comments, docstrings, log text and tests use the new names.
- OpenSpec: the capability `heartbeat-config` is renamed to `hostwatch-config`. Main specs that mention the old name are updated. Archived changes are left as they are.

This is a pure rename. Behavior, settings, message layout and timings do not change.

Out of scope: migrating an existing `slack-heartbeat` installation. None exists, because the first install happens after this change.

Assumptions about the current code, which differs slightly from the original request:
- The code is a package (`src/slack_heartbeat/`), not a single `slack_heartbeat.py`.
- No `.timer` units exist yet.
- The journal tag comes from the program's syslog ident, not from a `SyslogIdentifier=` line.

## Capabilities

### New Capabilities
- `hostwatch-config`: Replaces `heartbeat-config` under the new name. It covers the same requirements with the config at `/etc/hostwatch/config.ini`.

### Modified Capabilities
- `heartbeat-config`: Retired. All requirements move to `hostwatch-config`.
- `service-installation`: The install and uninstall requirements use the new paths and names.
- `slack-delivery`: The journal failure requirement uses the `hostwatch` journal tag.

## Impact

- **Code:** every file under `src/`, `bin/`, `systemd/`, `pam/` and `tests/`, plus `config.example.ini`, `install.sh`, `uninstall.sh` and `README.md`. Several files and directories are renamed.
- **Hosts:** none affected. Nothing is installed yet.
- **OpenSpec:** new main spec `hostwatch-config`. `heartbeat-config` is removed when this change is archived. `service-installation` and `slack-delivery` are updated. `openspec/changes/archive/` is untouched.
- **Name check:** once this change is archived, `grep -ri "slack-heartbeat\|slack_heartbeat"` outside `openspec/changes/archive/` returns nothing. Until then, it also matches this change's own artifacts and the main-spec text that archiving replaces.
