# Design

## Context

The service was built and archived as `add-slack-heartbeat` and has never been installed on any host. The journal tag is set in code (`log.py` `IDENT`), not in the unit. For motivation see proposal.md (Why); for behavior see `specs/`.

## Goals / Non-Goals

**Goals:**
- Every identifier is renamed mechanically, with no behavior change.

**Non-Goals:**
- Migrating an installed `slack-heartbeat`. Nothing is installed, so migration code would be untestable dead weight that keeps the old name in the tree.
- Compatibility shims: no `slack-heartbeat` symlink, no old config path, no `SLACK_HEARTBEAT_CONFIG` fallback.
- Message layout and wording do not change, except where the product name appears.

## Decisions

### D1. Name mapping
| Old | New |
|---|---|
| `src/slack_heartbeat/` | `src/hostwatch/` |
| `bin/slack-heartbeat` | `bin/hostwatch` |
| `systemd/slack-heartbeat-boot.service` | `systemd/hostwatch-boot.service` |
| `pam/slack-heartbeat` | `pam/hostwatch` |
| `/usr/local/lib/slack-heartbeat` | `/usr/local/lib/hostwatch` |
| `/etc/slack-heartbeat/` | `/etc/hostwatch/` |
| `SLACK_HEARTBEAT_CONFIG` | `HOSTWATCH_CONFIG` |
| syslog ident `slack-heartbeat` | `hostwatch`, plus `SyslogIdentifier=hostwatch` in the unit |
| Footer / test header / fallback "slack-heartbeat" | "HostWatch" |
| User-Agent `slack-heartbeat` | `hostwatch` |

- The display name "HostWatch" appears only in human-facing text: README, Slack footer and test message, unit `Description=` and PAM profile `Name:`.
- `SLACK_WEBHOOK_URL`, the install-time variable, keeps its name. It names the Slack webhook, not the product.
- The capability `slack-delivery` keeps its name for the same reason.
- The files were never committed, so they are renamed with plain `mv`. There is no history for `git mv` to keep.

### D2. Capability rename via retirement
OpenSpec has no operation for renaming a capability. `hostwatch-config` is added with the same requirements (new path), and `heartbeat-config` is retired:
- every one of its requirements is listed under REMOVED, pointing to its replacement
- `retire_capabilities: true` is set in `.openspec.yaml`, so archiving deletes the old main spec

### D3. The name check
After archiving, this command must print nothing:

```
grep -rniI "slack-heartbeat\|slack_heartbeat" --exclude-dir=.git --exclude-dir=archive .
```

Before archiving it also matches two things, both resolved by the archive:
- this change's artifacts, which move to `archive/`
- the main-spec requirement text, which the deltas replace (`service-installation`, `slack-delivery`) or delete (`heartbeat-config`)

A delta spec cannot change a Purpose, so the Purpose lines of the main specs are edited directly during apply.

## Risks / Trade-offs

- [The archived `add-slack-heartbeat` change and its tasks still use the old name] → Intended. Archives are history.
- [Anyone following the archived change's acceptance steps would use old commands] → The archived change was superseded before any install. The README and current specs are the reference.
