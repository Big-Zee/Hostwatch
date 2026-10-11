# Proposal

## Why

The review in `docs/security-review-2026-10-11.md` found 21 issues. None is critical or high, but several medium ones break the specs or leak data:
- an offline boot is held back by HostWatch's network ordering (Finding #1)
- the installed command can run code from `/usr/local/src` as root (Finding #6)
- a malformed webhook URL puts the secret in the journal (Finding #7)
- any local user can inject Slack mentions through a process name (Finding #8)

This change fixes every finding whose fix is small and low-risk, and records why the rest are deferred or rejected. Boot, shutdown and login safety come first.

## What Changes

Fixed (each fix keeps boot, shutdown and login independent of HostWatch succeeding):

- **Finding #1, boot delay:** `multi-user.target` no longer waits for `network-online.target` because of HostWatch.
  - The boot unit drops systemd's default dependencies and declares the ones it needs explicitly, so the target no longer waits for it.
  - The shutdown unit is ordered after `network.target` instead of `network-online.target`. It is still stopped before the network goes down.
- **Finding #2, repeated boot message:** the boot unit stays active after it finishes and is ignored by `systemctl isolate`. Switching targets no longer sends a second boot message or a false unclean-shutdown warning.
- **Finding #4, login child lifetime:** the detached login sender ends itself after 60 s at most.
- **Finding #6, code from `/usr/local/src`:** the installed command only loads `/usr/local/lib/hostwatch`. Checkout mode is used only when the command is not the installed copy and the checkout really contains the package.
- **Finding #7, webhook in logs:**
  - A webhook URL with whitespace or control characters (for example an inline `# comment`) is a configuration error.
  - Delivery errors and unexpected errors are logged without exception text that could carry the URL.
- **Finding #8, Slack injection:**
  - Process names and users in the heartbeat table are escaped, and backticks are neutralised, so they cannot end the code block or create mentions or links.
  - The plain-text fallback is escaped as well.
- **Finding #9, webhook on the command line:** the README and the `install.sh` header no longer recommend `sudo SLACK_WEBHOOK_URL=… ./install.sh`. They recommend the hidden prompt, or `--preserve-env`. `install.sh` also rejects a webhook containing whitespace.
- **Finding #10, config permissions:** every install run resets `/etc/hostwatch/config.ini` to `root:root 600`.
- **Finding #11 (part), environment override:** `HOSTWATCH_CONFIG` is ignored by the login hook, which runs as root with the PAM environment. Dry runs still honour it.
- **Finding #12, PAM silent no-op:**
  - `install.sh` checks that the hook line is in `/etc/pam.d/common-session` and fails loudly when it is not.
  - `uninstall.sh` stops before removing anything when the line is still there after `pam-auth-update --remove`.
- **Finding #13, marker on re-run:** the clean-shutdown record is written only when `/var/lib/hostwatch` is first created.
- **Finding #15, heartbeat at install:** documented (README). The schedule is unchanged.
- **Finding #16, uninstall leftovers:**
  - The boot unit is stopped as well as disabled.
  - Failed HostWatch units are reset.
  - The `systemctl disable` steps run even when a unit file is already missing.
- **Finding #18, boot unit failures:**
  - `hostwatch boot` catches unexpected errors, so a bug or a bad byte cannot fail the unit and mark boot "degraded".
  - The config is read as UTF-8 with an optional BOM. Invalid UTF-8 in the config is a configuration error.
  - Command output is decoded with replacement characters.
- **Verification hygiene:**
  - `bandit` flags `urlopen` (B310, medium). `slack.post` gets its own `https://` check and a justified `# nosec B310`.
  - A test string `/tmp/env.ini` (B108, medium) is changed.

Deferred (not fixed in this change):

- **Finding #3, PAM start-up cost:** a performance issue, not a safety defect, because the hook never blocks or fails a login. The fix means moving the service filter or the fork ahead of the package imports, which restructures the entry point. Measure on target hardware first.
- **Finding #5, shutdown time budget:** `TimeoutStopSec=10` already guarantees that shutdown is not held up. The remaining effects only appear when `systemctl` does not answer within 2 s: a lost message, or a false unclean warning. A whole-run deadline touches every collector, which is not a small fix.
- **Finding #11 (part), bare command names:** in every context `PATH` comes from root-controlled sources: systemd's fixed path, PAM environment files owned by root, or Python's default path. There is no exploit path. Hard-coding binary locations risks breaking hosts where they differ.
- **Finding #14, non-atomic install:** a failed install leaves logins safe (the PAM line is `optional`) and is repaired by re-running. Staging and swapping the package adds complexity to a root script for a rare case.
- **Finding #19, Slack field limits:** fixing it needs a truncation rule for the Users and Local IP fields. That is a message-content change, which this change excludes. It only affects hosts with roughly 50 or more sessions or addresses.
- **Finding #20, logind race:** the fallback to `who` still yields a list. Querying sessions one by one adds subprocess calls to the shutdown path, which is time-boxed.
- **Finding #21, heartbeat deadline / Retry-After:** blocking NSS lookups cannot be interrupted reliably with the standard library without restructuring the sampler. `Retry-After` has no effect on single-attempt heartbeats and changes boot retry timing.

Rejected:

- **Finding #17, slack-heartbeat migration:** not applicable. The rename design records that slack-heartbeat was never installed on any host. Its name check forbids the old name outside the archive, which detection code in `install.sh` would break.

Assumptions:
- `pam-auth-update --package` silently skips hand-edited `common-*` files (Finding #12). The install-time check is harmless if it does not, and the VM tasks confirm the behaviour.
- For Finding #2, `RemainAfterExit` plus `IgnoreOnIsolate` replaces the review's suggested boot-ID record. A boot-ID record would suppress the boot message after `systemctl soft-reboot`, because the kernel boot ID survives a soft reboot.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `boot-notification`: the boot target is never held back by HostWatch's network ordering (Finding #1). One message per boot also holds across target switches (Finding #2). Unexpected errors never fail the unit (Finding #18).
- `login-notification`: background delivery is bounded in time (Finding #4). The login hook ignores the config-path environment override (Finding #11).
- `message-identity`: values taken from the host are shown literally and cannot create Slack formatting, mentions or links, or end the process table (Finding #8).
- `hostwatch-config`:
  - A webhook URL containing whitespace or control characters is invalid (Finding #7).
  - A UTF-8 BOM is accepted and invalid UTF-8 is a reported error (Finding #18).
  - Re-installing restores the config file's permissions (Finding #10).
- `slack-delivery`: the "never exposed" requirement covers malformed URLs and unexpected errors (Finding #7).
- `service-installation`:
  - The installed command runs only installed code (Finding #6).
  - The documented webhook hand-over keeps the URL off command lines (Finding #9).
  - Install and uninstall verify the PAM hook (Finding #12).
  - A re-install keeps the clean-shutdown record (Finding #13).
  - Uninstall also stops the boot unit and clears failed units (Finding #16).

## Impact

- **Units:** `systemd/hostwatch-boot.service`, `systemd/hostwatch-shutdown.service`.
- **Code:**
  - `bin/hostwatch`
  - `src/hostwatch/cli.py`, `config.py`, `slack.py`, `messages.py`, `processes.py`, `sessions.py`, `netinfo.py`
  - their tests
- **Scripts:** `install.sh`, `uninstall.sh`. Re-running `install.sh` applies every fix to an existing install. The new wrapper, units and permission reset all take effect on re-run.
- **Docs:** `README.md`, plus a Resolution section in `docs/security-review-2026-10-11.md`.
- **Dependencies:** none added. Python standard library only.
- **Behaviour visible to users:** message content and schedules are unchanged, except that names containing `& < >` or a backtick are shown escaped. A webhook with an inline comment is now rejected with a clear error instead of failing at send time.
