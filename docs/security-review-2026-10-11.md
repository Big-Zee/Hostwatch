# HostWatch security review — 2026-10-11

Scope: the whole repository at commit `5b7a7d1` (main), reviewed against `openspec/specs/`. No code was changed.

Method: static review of the Python package, systemd units, PAM profile and install/uninstall scripts. Two findings (#7 and #8) were reproduced locally. The systemd and PAM findings come from reading the files and have not been tested on an Ubuntu host. The unit tests passed at the time of review (127 tests, `python -m unittest discover -s tests -t .`).

## Summary

No critical boot or login risks were found. The PAM line is `optional`, the hook gets out of the login path quickly, and the shutdown hook cannot hold up shutdown for more than about 10 seconds.

The most serious issues are an offline boot delay that breaks the spec (#1), the installed program trusting code in `/usr/local/src` (#6), and two ways secrets or untrusted text leak, into the journal (#7) and into Slack (#8).

Suggested fix order: #1, #6, #7 and #8, then #18 and #12.

| # | Severity | Area | Finding |
|---|---|---|---|
| 1 | Medium | Boot | Offline boots wait up to 60–120 s for the network |
| 2 | Medium | Boot | Second, false "Boot" message after `systemctl isolate` |
| 3 | Low | Login | Every PAM session pays for a full root Python start |
| 4 | Low | Login | Background login process has no time or rate limit |
| 5 | Low | Shutdown | Shutdown can run out of time, or misreport a clean shutdown |
| 6 | Medium | Security | Installed program loads code from `/usr/local/src` as root |
| 7 | Medium | Security | Webhook secret logged when the URL is malformed |
| 8 | Medium | Security | Local users can inject Slack formatting via process names |
| 9 | Low/medium | Security | README install command exposes the webhook |
| 10 | Low | Security | Existing config file permissions never checked |
| 11 | Low | Security | Environment overrides honoured while running as root |
| 12 | Medium | Installer | PAM hook install/removal can fail silently |
| 13 | Medium-low | Installer | Re-running the installer can hide the next crash |
| 14 | Low | Installer | Installs and upgrades are not atomic |
| 15 | Low | Installer | Fresh install on a long-running host sends a heartbeat at once |
| 16 | Low | Uninstaller | Uninstall leaves things behind |
| 17 | Low/info | Migration | No slack-heartbeat → hostwatch migration |
| 18 | Medium | Robustness | Boot unit can still fail and mark boot "degraded" |
| 19 | Low | Robustness | Very long fields make Slack reject the message |
| 20 | Low | Robustness | One ended session discards the whole logind result |
| 21 | Low | Robustness | Heartbeat can fail its unit or ignore Slack's back-off |

## Boot and login safety

### 1. Medium: offline boots wait up to 60–120 s for the network

- **Where:** `systemd/hostwatch-boot.service:4-5,21`, `systemd/hostwatch-shutdown.service:5-6,25`
- **Problem:** Both units are `WantedBy=multi-user.target`, and systemd makes a target wait for every unit it wants. Both units are also `After=` and `Wants=network-online.target`. So `multi-user.target` (and `graphical.target`) now wait for NetworkManager-wait-online (60 s by default) or networkd-wait-online (120 s by default).
  - The shutdown unit is `oneshot`, so its start always blocks. The boot unit being `simple` doesn't help, because it can't start until the network is online.
  - SSH and GDM are not ordered after `multi-user.target`, so logins still work. But this breaks the spec's "Boot is never delayed / Offline boot completes in its usual time" requirement.
- **Fix:**
  - **Boot unit:** set `DefaultDependencies=no` and add back `After=sysinit.target`, `Conflicts=shutdown.target` and `Before=shutdown.target`. Alternatively, start it from a `hostwatch-boot.timer` with `OnBootSec=1s`.
  - **Shutdown unit:** drop `Wants=network-online.target` and use `After=network.target nss-lookup.target`. Shutdown ordering still holds, because NetworkManager is `Before=network.target`.
  - **Verify:** run `systemd-analyze critical-chain multi-user.target` with the cable unplugged.

### 2. Medium: a second, false "Boot" message after `systemctl isolate`

- **Where:** `systemd/hostwatch-boot.service:9`, `src/hostwatch/cli.py:60`
- **Problem:** The boot unit has no `RemainAfterExit`. Running `systemctl isolate multi-user.target`, `isolate graphical.target` or `start multi-user.target` starts it again. That sends a second Boot message, and because the clean-shutdown marker was already used up, it says "previous shutdown was not clean". This breaks "exactly one per boot".
- **Fix:** add `RemainAfterExit=yes`. Also save `/proc/sys/kernel/random/boot_id` in `/var/lib/hostwatch` and skip the message when it matches the current boot.

### 3. Low: every PAM session pays for a full root Python start before the hook returns

- **Where:** `src/hostwatch/cli.py:6,199`, `pam/hostwatch:7`
- **Problem:** The hook runs on every open and close for every service that includes `common-session`, including `su` and `su -l`. It imports the whole package first (urllib, ssl, zoneinfo and so on), and only then filters by service and forks. That adds roughly 100–200 ms to each login or `su`, more on a cold cache.
- **Fix:** in `bin/hostwatch`, check that `PAM_TYPE` is `open_session` and that `PAM_SERVICE` is in the list before importing `cli`. Fork before the heavy imports.

### 4. Low: the background login process has no time limit or rate limit

- **Where:** `src/hostwatch/cli.py:187-220`
- **Problem:** The detached child runs as root inside the user's session scope. It can live for about 50 s or more: a 3 s wait, 3 attempts × 10 s timeout, 7 s of retry delays, and DNS lookups that no timeout covers. That keeps a quickly closed session in "closing" state. Automation that opens many SSH connections while Slack is down spawns one root Python per session.
- **Fix:** put `signal.alarm(60)` in the child. Optionally rate-limit with a lock file.

### 5. Low: shutdown can run out of time before sending, or misreport a clean shutdown

- **Where:** `src/hostwatch/cli.py:142-146`, `src/hostwatch/netinfo.py:52`
- **Problem:**
  - The command calls run one after another: `systemctl` 2+2 s, `ip` 5 s, `loginctl` 2+2 s, `who` 2 s. That can use up all of `TimeoutStopSec=10` before the HTTP attempt even starts.
  - If `is-system-running` times out during a real shutdown, the code treats it as "not stopping". It then neither sends nor writes the marker, so the next boot falsely warns of an unclean shutdown.
- **Fix:** give the whole run one ~8 s deadline. When `is-system-running` gives no answer, fall back to checking `list-jobs` for `shutdown.target`.

## Security

### 6. Medium: the installed program loads code from `/usr/local/src`, as root

- **Where:** `bin/hostwatch:11-18`
- **Problem:** When installed as `/usr/local/bin/hostwatch`, the "checkout" check looks for `/usr/local/src/hostwatch`. If that directory exists, it is used instead of `/usr/local/lib/hostwatch`, for every PAM session, boot, shutdown and heartbeat.
  - On Debian-style permissions (`root:staff 2775`), anyone in `staff` can get code run as root this way.
  - Even on root-only permissions, `git clone … /usr/local/src/hostwatch` (an obvious place to put this repo) makes `hostwatch` load as an empty namespace package. Then `from hostwatch import cli` fails, the boot unit fails (system "degraded"), and all notifications stop.
- **Fix:** have `install.sh` install a wrapper that only uses `INSTALLED_LIB`, for example by stripping out the checkout branch. Or only take the checkout branch when `realpath(__file__)` is not `/usr/local/bin/hostwatch` and `src/hostwatch/cli.py` exists.

### 7. Medium: the webhook secret gets logged when the URL is malformed (reproduced)

- **Where:** `src/hostwatch/slack.py:21-24,56-57`, `src/hostwatch/config.py:98-103`
- **Problem:** `configparser` does not strip inline comments, so `webhook_url = https://…/SECRET # prod` keeps the comment in the value. `http.client` then raises `InvalidURL` with the full secret path in its message. `_describe` logs that message on every attempt, six times at boot. Reproduced output: `InvalidURL: URL can't contain control characters. '/services/T000/B000/SECRETTOKEN '`. On Ubuntu, members of the `adm` group can read the journal, and the first user account is usually one of them.
- **Fix:**
  - In `validate()`, parse the URL with `urlsplit`. Reject whitespace and control characters, and require `https` and a host (optionally `hooks.slack.com`).
  - In `_describe`, log only the exception class for `InvalidURL`/`ValueError`.
  - The catch-alls at `cli.py:120,160,217` also log `{exc}`; log only the class name there too.

### 8. Medium: any local user can inject Slack formatting through a process name (reproduced)

- **Where:** `src/hostwatch/processes.py:108-116`
- **Problem:** Process names (`comm`, up to 15 characters, set freely by any user) go into the heartbeat table without escaping. A busy-looping process named "` ```<!channel> `" closes the code block and pings `@channel` on every heartbeat (payload confirmed). Smaller variant: the plain-text fallback (`messages.py:113-117`) doesn't escape the user name, remote host or machine label.
- **Fix:**
  - Escape `& < >` in the name and user columns, and replace backticks and control characters.
  - Escape the fallback text too.

### 9. Low/medium: the README's install command exposes the webhook

- **Where:** `README.md:641`, `install.sh:5`
- **Problem:** `sudo SLACK_WEBHOOK_URL=… ./install.sh` puts the secret in shell history and in `ps` (sudo's arguments, visible to all users while it runs). sudo also logs variables set on its command line (`ENV=`) to the auth log.
- **Fix:** make the hidden prompt the recommended path. Add an option to read the webhook from stdin or a file.

### 10. Low: an existing config file's permissions are never checked

- **Where:** `install.sh:54-55`
- **Problem:** A config created by hand (for example with `cp`, giving mode 644) stays world-readable.
- **Fix:** run `chown root:root` and `chmod 600` on every install, and print a warning if they had to change.

### 11. Low (defence in depth): environment overrides are honoured while running as root

- **Where:** `src/hostwatch/config.py:37`, `src/hostwatch/state.py:16`, and the subprocess calls
- **Problem:**
  - `HOSTWATCH_CONFIG` and `HOSTWATCH_STATE_DIR` are read in the PAM path. There, the environment is the PAM environment, which `pam_env user_readenv` could fill from the user's own files on some setups.
  - Commands (`systemctl`, `ip`, `loginctl`, `who`) are looked up through `PATH`.
- **Fix:** ignore the environment overrides when `PAM_TYPE` is set. Use absolute paths for the commands.

## Installer and uninstaller

### 12. Medium: the PAM hook install and removal can fail without any message

- **Where:** `install.sh:128`, `uninstall.sh:33`
- **Problem:** If `/etc/pam.d/common-*` was edited by hand, `pam-auth-update --package` leaves it alone and still exits 0.
  - **Install:** it prints "Done", but there is no login hook.
  - **Uninstall:** the `pam_exec … hostwatch login` line stays after the program is deleted. Every login then logs an exec failure (the login itself still works, because the line is `optional`).
- **Fix:** after each call, `grep` `common-session` and fail or warn with the manual fix.

### 13. Medium-low: re-running the installer can hide the next crash

- **Where:** `install.sh:48-51`
- **Problem:** Each run recreates the clean-shutdown marker. A crash after a re-install is then reported as a clean shutdown.
- **Fix:** write the marker only on the first install (when `$STATE_DIR` does not exist yet).

### 14. Low: installs and upgrades are not atomic

- **Where:** `install.sh:38-41,89-91`
- **Problem:** The `*.py` files are deleted before the new ones are copied, so a failure in between leaves a broken package that PAM and the boot unit still run. A bad `interval_minutes` stops the install after the files and units were already copied but before `daemon-reload`.
- **Fix:** copy into a staging directory, then `mv` it into place. Check the interval before changing anything.

### 15. Low: a fresh install on a long-running host sends a heartbeat at once

- **Where:** `install.sh:118-121`
- **Problem:** `OnBootSec` has already passed, so starting the timer fires it straight away, possibly before a webhook is set. The same happens with `start` after the timer was stopped by hand. The spec only forbids this on a re-run, so this is a gap rather than a violation.
- **Fix:** document it, or make the first run after install relative to the timer's start rather than to boot.

### 16. Low: uninstall leaves things behind

- **Where:** `uninstall.sh:31-35,45,53-58`
- **Problem:**
  - The boot unit is disabled without `--now`, so if it is still retrying after boot it keeps running.
  - Failed units are not cleared with `reset-failed`.
  - The cleanup is skipped whenever its file is already gone: a hand-deleted unit file leaves its `*.wants` link behind, and a missing PAM profile leaves the line in `common-session`.
- **Fix:** run `disable --now` and `pam-auth-update --remove` regardless, with `|| true`. Add `systemctl reset-failed 'hostwatch-*'`.

### 17. Low/info: there is no slack-heartbeat → hostwatch migration

- **Where:** `openspec/changes/archive/2026-10-11-rename-to-hostwatch/design.md`
- **Problem:** The design says this is deliberate ("nothing is installed"). If any host ever ran slack-heartbeat, its PAM profile, `slack-heartbeat-boot.service` and `/etc/slack-heartbeat/config.ini` (which holds the secret) survive both scripts. That host would get duplicate boot and login messages.
- **Fix:** add a check to `install.sh` that refuses to continue, or prints cleanup commands, when those old paths exist.

## Spec correctness and robustness

### 18. Medium: the boot unit can still fail and mark boot "degraded"

- **Where:** `src/hostwatch/cli.py:56-77`, `src/hostwatch/config.py:49-55`, `src/hostwatch/sessions.py:31-34`
- **Problem:** `run_boot` has no catch-all, unlike the shutdown, heartbeat and login handlers. A `UnicodeDecodeError` can escape from:
  - the config, for example a non-UTF-8 `machine_name`
  - the text output of `loginctl` or `who`

  The unit then fails and boot is marked "degraded", which breaks the spec. A UTF-8 BOM in the config (edited on Windows) turns into "invalid syntax" and stops all notifications.
- **Fix:**
  - Wrap `run_boot` in `try/except Exception`.
  - Read the config with `encoding="utf-8-sig"` and turn decode errors into `ConfigError`.
  - Pass `errors="replace"` to the subprocess calls.

### 19. Low: very long fields make Slack reject the whole message

- **Where:** `src/hostwatch/messages.py:27-46`
- **Problem:** Slack limits each field to 2000 characters. Many sessions or addresses push Users or Local IP past that, and Slack answers HTTP 400. That isn't retried, so every message from that host fails.
- **Fix:** cap the list with "… and N more".

### 20. Low: one ended session throws away the whole logind result

- **Where:** `src/hostwatch/sessions.py:78-80`
- **Problem:** If one session ends between `list-sessions` and `show-session`, which is common at shutdown and logout, the whole logind result is dropped. The code falls back to `who`, which misses Wayland desktops.
- **Fix:** query sessions one at a time and skip the ones that are gone.

### 21. Low: the heartbeat can fail its unit or ignore Slack's back-off

- **Where:** `src/hostwatch/processes.py:61`, `systemd/hostwatch-heartbeat.service:11`, `src/hostwatch/slack.py:51-55`
- **Problem:**
  - User-name lookups (`pwd`) on LDAP or SSSD hosts can hang. A hang, or slow DNS, hits `TimeoutStartSec=30`, and the failed unit marks the system degraded.
  - On HTTP 429, the retries ignore Slack's `Retry-After` header.
- **Fix:** add an overall deadline to the heartbeat run, and honour `Retry-After`.

## Checked and fine

- **PAM profile:** `optional`, `quiet`, interactive sessions only, lowest priority. Logouts (`close_session`), `sudo` and `su` are ignored.
- **Detaching:** the hook double-forks with `setsid`, sends its output to /dev/null and returns before any network call.
- **Commands:** there is no `shell=True` anywhere; all commands are passed as argument lists.
- **Secret handling at install:** the webhook reaches `awk` through the environment, the temp file is created with `umask 077`, and the config is created as `600 root:root`.
- **Unit hardening:** `NoNewPrivileges`, `ProtectSystem=strict` and `ProtectHome`; the program runs with `python3 -I`.
- **Shutdown handling:** the clean marker is written before sending, and a unit restart, reinstall or uninstall sends nothing.
- **Timeouts:** every HTTP request and every command has a timeout.
- **Repository:** `config.ini` is git-ignored, and the tests use only fake webhooks.

## Resolution

Handled by the OpenSpec change `fix-security-review-findings` on branch `security-fixes`. Tasks refer to that change's `tasks.md`. The unit tests and static checks (bandit, shellcheck) pass. The checks on an Ubuntu 24.04 VM (tasks 8.2, 8.3 and section 9) are still to be run.

| Finding | Status | Fixed by / reason |
|---|---|---|
| #1 | Fixed | Tasks 6.1, 6.3, 6.4: the boot unit drops default dependencies, so `multi-user.target` no longer waits for it; the shutdown unit is ordered after `network.target` and `nss-lookup.target`, not `network-online.target`. |
| #2 | Fixed | Task 6.2: the boot unit has `RemainAfterExit=yes` and `IgnoreOnIsolate=yes`. A boot-ID record was not used, because the kernel boot ID survives `systemctl soft-reboot`. |
| #3 | Deferred | A performance issue, not a safety defect: the hook never blocks or fails a login. Moving the service filter or the fork ahead of the imports restructures the entry point; measure on target hardware first. |
| #4 | Fixed | Task 4.1: the detached login process calls `alarm(60)` and ends within 60 s. |
| #5 | Deferred | `TimeoutStopSec=10` already keeps shutdown from being held up. The remaining effects need `systemctl` to stall for 2 s, and a whole-run deadline touches every collector. |
| #6 | Fixed | Task 5.1: the installed command loads only `/usr/local/lib/hostwatch`; checkout mode needs a non-installed path and a real `src/hostwatch/cli.py`. |
| #7 | Fixed | Tasks 1.1–1.3: a webhook with whitespace, control characters or no host is a config error; malformed-URL and unexpected errors are logged by type and location only; `slack.post` checks `https://` itself. |
| #8 | Fixed | Tasks 3.1, 3.2: process-table cells are escaped and backticks neutralised; the plain-text fallback is escaped. |
| #9 | Fixed | Tasks 7.3, 7.6: README and `install.sh` recommend the hidden prompt or `--preserve-env`; `install.sh` refuses a webhook with whitespace. |
| #10 | Fixed | Task 7.2: every install run resets the config to `root:root 600`. |
| #11 | Fixed in part, deferred in part | Task 4.2: the login hook ignores `HOSTWATCH_CONFIG`. Deferred: bare command names, because `PATH` always comes from root-controlled sources, and hard-coded paths risk breaking hosts. |
| #12 | Fixed | Tasks 7.4, 7.5: install and uninstall check `common-session` for the hook line and fail loudly; uninstall stops before removing anything. |
| #13 | Fixed | Task 7.1: the clean-shutdown record is written only when `/var/lib/hostwatch` is first created. |
| #14 | Deferred | A failed install leaves logins safe (the PAM line is `optional`) and is repaired by re-running; staging and swapping adds complexity for a rare case. |
| #15 | Fixed (documented) | Task 7.6: the README says a first install on a long-running host sends one heartbeat right away. The schedule is unchanged. |
| #16 | Fixed | Task 7.5: uninstall stops the boot unit, disables units whose files are gone, removes the known enablement links and resets failed units. |
| #17 | Rejected | Not applicable: slack-heartbeat was never installed on any host, and its name check forbids the old name outside the archive. |
| #18 | Fixed | Tasks 2.1–2.3: `hostwatch boot` catches unexpected errors; the config is read as UTF-8 with an optional BOM, and invalid UTF-8 is a config error; command output is decoded with replacement. |
| #19 | Deferred | Needs a truncation rule for the Users and Local IP fields, a message-content change this change excludes; only hosts with about 50 or more sessions or addresses are affected. |
| #20 | Deferred | The `who` fallback still yields a list; querying sessions one by one adds subprocess calls to the time-boxed shutdown path. |
| #21 | Deferred | Blocking NSS lookups cannot be interrupted reliably with the standard library without restructuring the sampler; `Retry-After` has no effect on single-attempt heartbeats and would change boot retry timing. |
