# Tasks

Every task names the finding it fixes. Each commit message lists the findings its changes fix (e.g. "Finding #7"). Run the unit tests with `python3 -m unittest discover -s tests -t .`.

## 1. Webhook secret stays out of logs (Finding #7)

- [x] 1.1 Finding #7: in `config.validate`, reject a webhook containing whitespace or control characters, or with no host in `urlsplit`. The error must not quote the value and must mention that inline comments are not supported (design D6). Verify that new `tests/test_config.py` cases cover an inline `# prod` comment, an embedded space, a tab and a missing host, and that each `ConfigError` message contains no part of the URL.
- [x] 1.2 Finding #7: in `slack._describe`, return only the class name for `http.client.InvalidURL` and `ValueError`. In `slack.post`, refuse a non-`https://` URL before `urlopen`, log an error without the URL and return False, and mark the `urlopen` call `# nosec B310` with the reason. Verify that a `tests/test_slack.py` case posting to `https://hooks.slack.invalid/services/T0/B0/SECRETTOKEN x` logs no text containing `SECRETTOKEN`, and that a non-https URL is never passed to `urlopen`.
- [x] 1.3 Finding #7: add `cli._log_unexpected(event, exc)`, which logs `<event>: unexpected error: <Class> at <file>:<line>` from the innermost traceback frame. Use it in the existing catch-alls of `run_heartbeat`, `run_shutdown` and `run_login`. Verify with `tests/test_cli.py` cases that raise `RuntimeError("https://hooks.slack.com/services/SECRET")` inside each command and assert that the logged line names `RuntimeError` and a file and line, and does not contain `SECRET`.

## 2. Boot command cannot fail its unit (Finding #18)

- [x] 2.1 Finding #18: in `config.load`, open the config with `encoding="utf-8-sig"` and turn `UnicodeDecodeError` into `ConfigError("config <path> is not valid UTF-8")` (design D9). Verify that `tests/test_config.py` loads a BOM-prefixed config normally and that a config with a Latin-1 byte raises `ConfigError`.
- [x] 2.2 Finding #18: pass `errors="replace"` to `subprocess.run` in `sessions._run`, `netinfo._systemctl` and `netinfo.local_addresses`. Verify with tests in `tests/test_sessions.py` and `tests/test_netinfo.py` that each call is made with `errors="replace"`.
- [x] 2.3 Finding #18: wrap the body of `run_boot` after the clean-shutdown check in `try/except Exception`, logging through `_log_unexpected` and returning 0. Verify with a `tests/test_cli.py` case where `_identity` raises `UnicodeDecodeError`: `cli.main(["boot"])` returns 0 and the marker is still consumed exactly once.

## 3. Literal host values in Slack (Finding #8)

- [x] 3.1 Finding #8: in `processes.format_table`, fit and pad each user and name cell, then escape `& < >`, replace backticks with `ˋ` (U+02CB) and replace control characters with `?` (design D7). Verify that a `tests/test_processes.py` case for a row named ```` ```<!channel> ```` produces a table with exactly two triple-backtick fences and no `<!` sequence, and that the existing alignment tests for ordinary names pass unchanged.
- [x] 3.2 Finding #8: in `messages.build`, escape the plain-text fallback once, and leave the `plain_text` header unescaped. Verify that a `tests/test_messages.py` case with machine name `Lab <A&B>` gives the fallback `Lab &lt;A&amp;B&gt; · …` and the header `:desktop_computer: Lab <A&B> (host) · Boot`, and that all existing message tests still pass.

## 4. Login hook (Findings #4, #11)

- [x] 4.1 Finding #4: in `run_login`, call `signal.alarm(60)` in the detached child only, after `_detach()` returns True and before any work. Do not install a handler (design D4). Verify with a `tests/test_cli.py` case that patches `signal.alarm` and a fake `_detach` path: the real-detach branch calls `alarm(60)`, and injected-detach and dry-run calls do not.
- [x] 4.2 Finding #11: in `run_login`, when the run is not a dry run and no `--config` was given, load `config.DEFAULT_PATH` explicitly so `HOSTWATCH_CONFIG` is ignored (design D8). Verify two `tests/test_cli.py` cases: with `HOSTWATCH_CONFIG` set in the environment, a non-dry-run login loads `/etc/hostwatch/config.ini`; and the README's dry-run example with `HOSTWATCH_CONFIG` still uses that file.

## 5. Installed wrapper (Finding #6)

- [x] 5.1 Finding #6: in `bin/hostwatch`, use `<checkout>/src` only when `realpath(__file__)` is not `/usr/local/bin/hostwatch` and `<checkout>/src/hostwatch/cli.py` exists; otherwise use `/usr/local/lib/hostwatch` (design D5). Verify that `python3 bin/hostwatch test --dry-run --config config.example.ini` still works from the checkout. Verify that a new `tests/test_wrapper.py` case shows the path choice: run the wrapper's selection logic with a fake real path `/usr/local/bin/hostwatch` and an existing `/usr/local/src/hostwatch/cli.py` (in a temporary tree) and assert that the installed library is chosen.

## 6. Systemd units (Findings #1, #2)

- [x] 6.1 Finding #1: in `systemd/hostwatch-boot.service`, set `DefaultDependencies=no` with `Requires=sysinit.target`, `After=sysinit.target basic.target network-online.target`, `Wants=network-online.target`, `Conflicts=shutdown.target` and `Before=shutdown.target` (design D1). Verify that `grep -c DefaultDependencies=no systemd/hostwatch-boot.service` prints 1. Unit checks follow in 8.3 and 9.2.
- [x] 6.2 Finding #2: add `RemainAfterExit=yes` and `IgnoreOnIsolate=yes` to `systemd/hostwatch-boot.service` (design D3), and update its comments. Verify in the VM (9.3) that `systemctl isolate multi-user.target` and a round trip through `rescue.target` send no second boot message.
- [x] 6.3 Finding #1: in `systemd/hostwatch-shutdown.service`, replace `Wants=` and `After=network-online.target` with `After=network.target nss-lookup.target`, and update the comment that explains the stop ordering (design D2). Verify in the VM (9.2, 9.4) that the shutdown message still arrives on poweroff and reboot.
- [x] 6.4 Findings #1, #2: update the README's "Shutdown and unclean-shutdown detection" section and the boot ordering description to match the new units. Verify that the README no longer says the shutdown unit is ordered after `network-online.target`.

## 7. Installer, uninstaller and README (Findings #9, #10, #12, #13, #15, #16)

- [x] 7.1 Finding #13: in `install.sh`, create `/var/lib/hostwatch` and the clean marker only when the directory does not exist. Verify in the VM (9.6) that a re-run on an installed host leaves an absent marker absent.
- [x] 7.2 Finding #10: in `install.sh`, after the config block, reset an existing config to `root:root 600` when `stat -c '%U:%G %a'` differs, and print that it was corrected. Verify in the VM (9.6) that `chmod 644 /etc/hostwatch/config.ini && sudo ./install.sh` leaves `-rw------- root root` and unchanged content (`sha256sum` before and after).
- [x] 7.3 Finding #9: in `install.sh`, refuse a supplied webhook that matches `[[:space:][:cntrl:]]` without printing it, and keep the placeholder. Change the header comment to show the prompt and the `--preserve-env=SLACK_WEBHOOK_URL` form. Verify in the VM (9.6) that a webhook ending in ` # prod` is refused and the placeholder kept.
- [x] 7.4 Finding #12: in `install.sh`, after `pam-auth-update --enable`, check `/etc/pam.d/common-session` for the hook line. If it is missing, print the manual fix and exit 1. Verify in the VM (9.6) by hand-editing `common-session` before a fresh install.
- [x] 7.5 Findings #12, #16: in `uninstall.sh`:
  - after the PAM step, check for the hook line regardless of whether the profile exists, and if it is still there, print the manual fix and exit 1 before removing anything else
  - run every `systemctl disable` without file-existence guards and with `|| true`
  - disable the boot unit with `--now`
  - remove the three known `*.wants` links explicitly
  - run `systemctl reset-failed` for each HostWatch unit after `daemon-reload`

  Verify in the VM (9.6) using the spec scenarios "Uninstall shortly after boot", "Unit file already deleted" and "Hand-edited PAM configuration at uninstall".
- [x] 7.6 Findings #9, #15: in `README.md`, replace `sudo SLACK_WEBHOOK_URL=… ./install.sh` (Install and "Using HostWatch on several machines") with the hidden prompt and the `read -rs` / `--preserve-env` form, and say why. Add to the Heartbeat section that a first install on a host up longer than one interval sends one heartbeat right away. Document the new `install.sh` failure for a hand-edited `common-session`. Verify with `grep -n "sudo SLACK_WEBHOOK_URL=" README.md install.sh`, which must print nothing.

## 8. Static verification

- [x] 8.1 Change `/tmp/env.ini` in `tests/test_config.py` to `/etc/hostwatch-test/env.ini` (bandit B108, design D11). Then run `bandit -r .` and verify that it reports no medium or high issues; any remaining low findings are the ones listed in design D11.
- [ ] 8.2 Run `shellcheck install.sh uninstall.sh` on Ubuntu 24.04 and verify that it prints no warnings. Fix any it reports.
- [ ] 8.3 Run `systemd-analyze verify systemd/hostwatch-boot.service systemd/hostwatch-shutdown.service systemd/hostwatch-heartbeat.service systemd/hostwatch-heartbeat.timer` on Ubuntu 24.04 (after install, against the paths in `/etc/systemd/system/`) and verify that it reports nothing.
- [x] 8.4 Run the full unit test suite and verify that it passes with more tests than the 127 before this change.

## 9. VM verification (Ubuntu 24.04 desktop, real webhook)

- [ ] 9.1 Install with `sudo ./install.sh` (hidden prompt), run `sudo hostwatch test`, then reboot. Verify one test message, one "Rebooting" message, one boot message with no unclean warning, and `systemctl --failed` showing no HostWatch unit.
- [ ] 9.2 With the network cable unplugged (or Wi-Fi off), reboot. Verify:
  - the boot takes its usual time
  - `systemd-analyze critical-chain multi-user.target` contains no HostWatch unit and no wait on `network-online.target` caused by HostWatch
  - after reconnecting within the retry window, the boot message arrives
  - the boot unit is not failed (Finding #1)
- [ ] 9.3 Run `sudo systemctl isolate multi-user.target`, then `sudo systemctl isolate graphical.target`, then a round trip through `rescue.target`. Verify that no extra boot message is sent (Finding #2).
- [ ] 9.4 Log in as a non-admin user on the desktop and over SSH, then run `sudo poweroff`. Verify:
  - one Graphical and one SSH login message, each without noticeable delay
  - one "Shutting down" message
  - the next boot message has no unclean warning
- [ ] 9.5 Make Slack unreachable (for example, point `hooks.slack.com` at `203.0.113.1` in `/etc/hosts`, or block outbound 443). Then boot, log in on the desktop and over SSH, and shut down. Verify:
  - boot, login and shutdown complete normally
  - shutdown takes at most about 10 s longer
  - no HostWatch process remains 60 s after a login (Finding #4)
  - the journal (`journalctl -t hostwatch`) shows the failures without any part of the webhook URL
  - `systemctl --failed` shows no HostWatch unit
- [ ] 9.6 Installer and uninstaller checks for tasks 7.1–7.5:
  - re-run with the marker absent
  - config set to 644
  - webhook with ` # prod`
  - hand-edited `common-session` at install and at uninstall
  - uninstall within 2 minutes of boot
  - uninstall after deleting `hostwatch-boot.service` by hand
  - `uninstall.sh --purge`

  Verify that each behaves as its spec scenario says, and that afterwards `systemctl list-unit-files 'hostwatch*'`, `ls /etc/systemd/system/*.wants/ | grep hostwatch` and `grep hostwatch /etc/pam.d/common-session` all print nothing.
- [ ] 9.7 Set a webhook with an inline comment in `/etc/hostwatch/config.ini` and reboot. Verify that the journal says the webhook URL is invalid, contains no part of the URL, and that the boot unit is not failed (Findings #7, #18).

## 10. Close-out

- [x] 10.1 Add a "Resolution" section to `docs/security-review-2026-10-11.md`. It marks every finding #1–#21 as fixed, deferred or rejected, with the reason for deferred and rejected ones (from proposal.md) and the task that fixed each fixed one. Verify that all 21 numbers appear exactly once in that section.
- [x] 10.2 Commit the work with messages that list the finding numbers each commit fixes, and a final summary naming deferred findings #3, #5, #11 (command paths), #14, #19, #20, #21 and rejected finding #17. Verify with `git log --format=%B security-fixes ^main | grep -o "Finding #[0-9]*" | sort -u`, which must cover every fixed finding.

## Workflow follow-up

- After the VM checks pass and the branch is reviewed, archive with `/opsx:archive` to sync the delta specs into `openspec/specs/`.
