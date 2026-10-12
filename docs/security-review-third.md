# HostWatch security review (third pass): 2026-10-11

Scope: the whole repository at commit `b301131` (branch `fix-heartbeat-timer-and-reuse-config`), reviewed against `openspec/specs/` and the open change `fix-heartbeat-timer-and-reuse-config`. No code was changed. Findings already recorded in [security-review-2026-10-11.md](security-review-2026-10-11.md) and [security-review-second.md](security-review-second.md) are not repeated; they are listed under [Open items carried over](#open-items-carried-over).

Method: static review of `src/`, `bin/`, `systemd/`, `pam/`, `install.sh`, `uninstall.sh`, `openspec/specs/` and the open change. Findings #6 and #9 were reproduced locally. The systemd and PAM findings come from reading the files and have not been tested on an Ubuntu host; each says how to check it on a VM. The unit tests pass (189 tests, `python -m unittest discover -s tests -t .`).

## Summary

**No critical boot or login risks were found.** Nothing in HostWatch can stop the host from booting, hold up shutdown for more than about 10 seconds, or block a login.

There are four medium findings: one security exposure that depends on the host's PAM configuration (#1), and three real bugs. Two of them (#8 and #9) are in this branch's own changes.

Suggested fix order: #8 and #9, then #1, then #2.

| # | Severity | Area | Finding |
|---|---|---|---|
| 1 | Medium (high where the condition holds) | Login / Security | Root login hook trusts the PAM environment |
| 2 | Medium | Login | Every non-interactive SSH connection is announced as a login |
| 3 | Low | Shutdown | Reboot from `rescue.target` is reported as unclean |
| 4 | Low | Login | Errors while detaching escape the login hook's catch-all |
| 5 | Low | Boot | Boot message up to 2 minutes late on multi-interface hosts |
| 6 | Low | Security | Slack formatting from host values is still interpreted |
| 7 | Low | Security | Documented install flow leaves the webhook exported in the admin's shell |
| 8 | Medium | Installer | A shorter interval sends a heartbeat during install |
| 9 | Medium | Installer | `--reconfigure` can report "Webhook replaced" without changing anything |
| 10 | Low | Installer | Hook-line check also matches a commented-out line |
| 11 | Low | Uninstaller | Uninstall skips `pam-auth-update` when the profile file is gone |
| 12 | Low | Installer | Interrupted install leaves things behind |
| 13 | Low | Installer | Misleading errors on Python < 3.9 or a non-UTF-8 machine name |
| 14 | Low/info | Migration | No slack-heartbeat → hostwatch migration guard |

## Boot, shutdown and login safety

### 1. Medium (high where the condition holds): the root login hook trusts the PAM environment

- **Where:** `pam/hostwatch:7`, `bin/hostwatch:29-34`, `src/hostwatch/netinfo.py:58,80`, `src/hostwatch/sessions.py:32`, `src/hostwatch/slack.py:53`
- **Problem:** `pam_exec` starts the hook as root with the PAM environment, and nothing cleans it. If any announced login service (`gdm-password`, `lightdm`, `sddm`, `login`, `sshd`) runs `pam_env.so user_readenv=1` before `@include common-session`, the user's `~/.pam_environment` controls the hook's environment:
  - `PATH`: `loginctl`, `ip`, `who` and `systemctl` are looked up through it, so a user's own `~/bin/loginctl` would run as root.
  - `LD_PRELOAD`: loaded into `python3` and every command it runs, as root.
  - `OPENSSL_CONF`, `SSL_CERT_FILE` and `https_proxy`: together they allow a man-in-the-middle on the TLS connection, which reveals the webhook.

  On stock Ubuntu this is probably not exploitable: Ubuntu moved `pam_env` after `common-session` for lightdm and gdm ([lightdm change](https://bazaar.launchpad.net/~mterry/lightdm/ubuntu-qt5/revision/1128), [gdm3 bug](https://bugs.qastaging.launchpad.net/ubuntu/+source/gdm3/+bug/1748036)). But that depends on files HostWatch does not control, and `user_readenv` is deprecated upstream for exactly this reason ([Arch FS#68945](https://bugs.archlinux.org/task/68945)).
- **Fix:**
  - In `bin/hostwatch`, before any import, when `PAM_TYPE` is set and this is not a dry run, replace `os.environ` with only the `PAM_*` variables plus `PATH=/usr/sbin:/usr/bin:/sbin:/bin` and `LANG=C.UTF-8`. This must happen before `cli` imports `ssl`.
  - Call the commands by absolute path (finding #11 of the first review, deferred).
  - `LD_PRELOAD` on `python3` itself cannot be fixed inside Python. Have `install.sh` warn when `grep -n 'user_readenv=1\|common-session' /etc/pam.d/{sshd,login,gdm-*,lightdm*,sddm*}` shows `user_readenv=1` before the include.

### 2. Medium: every non-interactive SSH connection is announced as a login

- **Where:** `src/hostwatch/cli.py:14-15,28-32`
- **Problem:** sshd opens a PAM session for every connection, not only interactive ones. `scp`, `rsync`, `git` over SSH, Ansible and monitoring probes each:
  - post a "Login" message, against the spec's "interactive login" wording;
  - start a root Python process that lives up to 60 s.

  Backup or configuration-management jobs can flood the channel, trigger HTTP 429, and spawn many root processes.
- **Fix:**
  - Announce SSH only when a terminal was allocated. Check on a VM what `PAM_TTY` holds for `ssh host true` and for an interactive `ssh host`.
  - Alternatively, add `[login] ignore_users` / `ignore_noninteractive` settings.
  - Add a simple rate limit, for example a timestamp file per user and remote host.

### 3. Low: a reboot from `rescue.target` is reported as an unclean shutdown

- **Where:** `systemd/hostwatch-shutdown.service` (has no `IgnoreOnIsolate=`)
- **Problem:** `systemctl rescue` (an isolate) stops the shutdown unit. Its stop action correctly sends nothing, because the system is not stopping. If the admin then reboots directly from rescue mode, there is no shutdown message and no clean-shutdown record, so the next boot falsely warns "not clean". The spec only covers isolating to rescue and coming back.
- **Fix:** add `IgnoreOnIsolate=yes` to `hostwatch-shutdown.service`, as the boot unit already has.

### 4. Low: errors while detaching escape the login hook's catch-all

- **Where:** `src/hostwatch/cli.py:230-241,258`
- **Problem:** `_detach()` runs outside the `try`. A failed fork, or `waitpid` raising `ChildProcessError` when the caller ignores `SIGCHLD`, makes the hook exit 1 with a traceback. On a TTY `login`, that traceback can appear on the console. The login itself still succeeds, because the PAM line is `optional`.
- **Fix:** wrap the `_detach()` call in `try/except Exception`, log it with `_log_unexpected`, and return 0.

### 5. Low: on hosts with several network interfaces, the boot message can arrive up to 2 minutes late

- **Where:** `systemd/hostwatch-boot.service:9-10`
- **Problem:** `systemd-networkd-wait-online` waits for every interface it manages, 120 s by default. With a NIC that is configured but has no cable, the boot message arrives about 2 minutes after the network was usable. The spec says "within seconds". Boot itself is not delayed.
- **Fix:** document this, or drop the `network-online.target` dependency and rely on the existing retries (5 s, 10 s, 20 s, …), which already cover a late network.

## Security

### 6. Low: Slack formatting from host values is still interpreted (reproduced)

- **Where:** `src/hostwatch/messages.py:15-16,72,77`
- **Problem:**
  - `_escape` only handles `& < >`. A user name or remote host containing `*`, `_`, `~` or a backtick is formatted: `a_b_*x*_~y~` is passed through unchanged.
  - mrkdwn text objects leave `verbatim` at its default of false, so Slack auto-links URLs and can parse some mentions.
  - The message-identity spec says host values "SHALL NOT create a … link or text formatting".
- **Fix:** set `"verbatim": True` on every mrkdwn object, and escape the formatting characters (for example with a zero-width joiner, or by using `plain_text` fields for host values).

### 7. Low: the documented install flow leaves the webhook exported in the admin's shell

- **Where:** `install.sh:15-16`, `README.md:36-37,87-88`
- **Problem:** after `read -rs SLACK_WEBHOOK_URL && export SLACK_WEBHOOK_URL`, every program started later from that shell inherits the secret.
- **Fix:** document `sudo --preserve-env=SLACK_WEBHOOK_URL ./install.sh; unset SLACK_WEBHOOK_URL`, or run it in a subshell: `( read -rs SLACK_WEBHOOK_URL && export SLACK_WEBHOOK_URL && sudo --preserve-env=SLACK_WEBHOOK_URL ./install.sh )`.

## Installer and uninstaller

### 8. Medium: changing the interval to a shorter one sends a heartbeat during install

- **Where:** `install.sh:277-307`, `systemd/hostwatch-heartbeat.timer:12-13`
- **Problem:**
  - `OnUnitActiveSec` counts from the heartbeat service's last start, and `systemctl restart` of the timer does not reset that.
  - Example: the last heartbeat ran 40 minutes ago and the interval goes from 60 to 15. The next run is then computed as 25 minutes in the past, and systemd fires the timer straight away (at `daemon-reload` or at the restart).
  - The same happens on the upgrade path this branch targets, if the service was once started by hand.
  - This breaks the change's own scenarios "Re-run sends nothing" and "Interval changed on a long-running host".
- **Fix:**
  - Make `run_heartbeat` skip when the timer became active less than about 60 s ago. Read `ActiveEnterTimestampMonotonic` of `hostwatch-heartbeat.timer` and compare it with `CLOCK_MONOTONIC`; a real first run is always at least 5 minutes after activation.
  - **Check on a VM:** with the interval at 60, run the service once, wait 6 minutes, set the interval to 5, run `install.sh --yes`, then watch `journalctl -u hostwatch-heartbeat`.

### 9. Medium: `--reconfigure` can report "Webhook replaced" without changing anything (reproduced)

- **Where:** `install.sh:99-107,220-224`
- **Problem:**
  - The `awk` only rewrites a line matching `webhook_url *=`. configparser also accepts `webhook_url: …` and keys in other letter cases (`Webhook_URL`). A file whose webhook line was deleted or commented out has nothing to match either.
  - In all these cases the script makes a `.bak`, writes an unchanged file and prints "Webhook replaced".
  - An admin rotating a leaked webhook would believe the old one is gone. Once it is revoked in Slack, every notification fails with HTTP 404.
- **Fix:** after `set_webhook`, compare the masked value from `hostwatch config-summary` with the expected last 4 characters. Alternatively, let a Python helper set the key with configparser-aware matching (input passed through the environment), and fail loudly when the key is missing.

### 10. Low: the hook-line check also matches a commented-out line

- **Where:** `install.sh:70,327`, `uninstall.sh:18,39`
- **Problem:** `#session optional pam_exec.so … hostwatch login` matches the pattern. `install.sh` then reports the hook as active when it is not, and `uninstall.sh` refuses to run until the comment is deleted.
- **Fix:** anchor the pattern: `^[[:space:]]*session[[:space:]].*pam_exec\.so.*/usr/local/bin/hostwatch login`.

### 11. Low: uninstall skips `pam-auth-update` when the profile file is already gone

- **Where:** `uninstall.sh:33-48`
- **Problem:** if `/usr/share/pam-configs/hostwatch` was deleted, `pam-auth-update` is not run, so the generated line stays. The script then tells the admin to edit `common-session` by hand, when running `pam-auth-update --package` would have regenerated it correctly.
- **Fix:** run `pam-auth-update --package --remove hostwatch || pam-auth-update --package` every time, then do the existing check.

### 12. Low: an interrupted install leaves things behind

- **Where:** `install.sh:91,161,325`
- **Problem:**
  - The PAM profile is copied early but only enabled at the end. If the install aborts in between, any later `pam-auth-update --package` run by another package's postinst enables it anyway, because the profile has `Default: yes`.
  - An abort between `mktemp` and `commit_conf` leaves `/etc/hostwatch/.config.XXXXXX` behind. It is root-only (`600`) but holds the webhook, and `uninstall.sh` without `--purge` keeps it.
- **Fix:** copy the PAM profile just before `pam-auth-update`, and `trap 'rm -f "$tmp"' EXIT` in the config helpers. The rest is the deferred finding #14 of the first review (non-atomic installs).

### 13. Low: misleading errors on Python older than 3.9, or a non-UTF-8 machine name

- **Where:** `install.sh:144-149,243-249,268-270`, `src/hostwatch/config.py:6`
- **Problem:**
  - `zoneinfo` needs Python 3.9. On Ubuntu 20.04 (Python 3.8), every command fails to import, and `install.sh` stops with "fix [heartbeat] interval_minutes".
  - A machine name typed in a Latin-1 terminal makes the config invalid UTF-8, with the same misleading message, and every notification then fails.
- **Fix:**
  - Check `python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'` before installing.
  - Reject a name that is not valid UTF-8 (`iconv -f UTF-8 -t UTF-8`).
  - Have `heartbeat-interval` print the real error, not a fixed message.

### 14. Low/info: no slack-heartbeat → hostwatch migration guard

- **Where:** `install.sh` has no code for it. The first review rejected this (#17) on the grounds that slack-heartbeat was never installed anywhere.
- **Problem:** if that assumption is ever wrong, the old PAM profile and `slack-heartbeat-boot.service` survive, causing duplicate login and boot messages, and `/etc/slack-heartbeat/config.ini`, which holds a webhook, also survives.
- **Fix:** a cheap guard. If `/usr/share/pam-configs/slack-heartbeat`, `/etc/systemd/system/slack-heartbeat-boot.service` or `/etc/slack-heartbeat` exists, print the cleanup commands and exit 1.

## Correctness against `openspec/specs/`

Apart from the findings above (#2, #3, #5, #6, #8), the implementation matches the specs, with two small differences:

- **Heartbeat:** "Gathering … SHALL NOT send any network request" does not hold on LDAP or SSSD hosts, because the user lookups (`pwd.getpwuid`) go over the network. This also widens the deferred finding #21 of the first review.
- **logged-in-users:** sessions are only listed when logind reports `Class=user`. systemd 256 and later also has `user-early` and `user-light`, so on Ubuntu releases after 24.04, some sessions (root logins, for example) may be left out of the Users list. This only matters beyond the tested 24.04.

## Checked and fine

- **PAM profile:** the line is `optional` and `quiet`, interactive sessions only. The hook forks before any network or logind call, and the background process is bounded by `alarm(60)`.
- **Boot unit:** no default dependencies, `Type=simple` with a catch-all, so it never delays `multi-user.target` and never marks boot as degraded.
- **Shutdown unit:** capped at 10 s, and the clean-shutdown record is written before sending.
- **Commands:** no `shell=True`; every subprocess call and every HTTP request has a timeout.
- **Secret handling:** the webhook never appears in process arguments, logs or the installer's summary. The config and `.bak` are `root:root 600`, and temporary files are created with `umask 077` inside `/etc/hostwatch`.
- **Code loading:** `python3 -I`, and the installed command loads only the installed code.
- **Escaping:** the process table is escaped and cannot close its code block.
- **Idempotency:** re-runs leave the config, the drop-in and the clean-shutdown record unchanged.

## Open items carried over

- Deferred findings of the first review: #3 (Python start-up cost on every PAM session), #5 (shutdown time budget), #11 (bare command names), #14 (non-atomic install), #19 (Slack field length limit), #20 (one vanished session drops the whole logind result) and #21 (blocking user lookups, `Retry-After`).
- Tasks 5.1–5.7 of `openspec/changes/fix-heartbeat-timer-and-reuse-config/tasks.md` (shellcheck and the Ubuntu 24.04 VM checks) are not done yet.

## Sources

- [Arch FS#68945: user_readenv is deprecated](https://bugs.archlinux.org/task/68945)
- [Launchpad: .pam_environment not applied if home directory is encrypted (gdm3)](https://bugs.qastaging.launchpad.net/ubuntu/+source/gdm3/+bug/1748036)
- [lightdm Ubuntu PAM change (bazaar.launchpad.net)](https://bazaar.launchpad.net/~mterry/lightdm/ubuntu-qt5/revision/1128)
