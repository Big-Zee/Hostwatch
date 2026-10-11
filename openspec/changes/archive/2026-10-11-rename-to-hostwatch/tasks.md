# Tasks

## 1. Rename code and tests

- [x] 1.1 Rename `src/slack_heartbeat` to `src/hostwatch` and `bin/slack-heartbeat` to `bin/hostwatch`. In the wrapper, set `INSTALLED_LIB = "/usr/local/lib/hostwatch"`, look for `src/hostwatch`, and import `from hostwatch import cli`. Verify that `python3 bin/hostwatch --help` shows `usage: hostwatch`.
- [x] 1.2 Update the package to the new names:
  - `config.DEFAULT_PATH` becomes `/etc/hostwatch/config.ini` and `ENV_VAR` becomes `HOSTWATCH_CONFIG`
  - `log.IDENT` becomes `hostwatch`
  - argparse `prog="hostwatch"`
  - the `messages` footer and the test header and fallback say "HostWatch"
  - the `netinfo` User-Agent is `hostwatch`
  - module docstrings and comments use the new name

  Verify that `grep -rn "slack.heartbeat" src bin` prints nothing, and that `python3 bin/hostwatch test --dry-run --config config.example.ini` shows the footer `HostWatch` and the fallback `HostWatch test message from …`.
- [x] 1.3 Update the tests: imports become `from hostwatch import …`, and the expected footer, test text, default path and env var use the new names. Verify that `python3 -m unittest discover -s tests -t .` passes with the same number of tests as before (61) and that `grep -rn "slack.heartbeat" tests` prints nothing.

## 2. Rename system integration files

- [ ] 2.1 Rename `systemd/slack-heartbeat-boot.service` to `systemd/hostwatch-boot.service`. Set `Description=Slack notification when the host has booted (HostWatch)`, `ExecStart=/usr/local/bin/hostwatch boot` and add `SyslogIdentifier=hostwatch`. Verify `systemd-analyze verify /etc/systemd/system/hostwatch-boot.service` on Ubuntu after install.
- [ ] 2.2 Rename `pam/slack-heartbeat` to `pam/hostwatch`. Set `Name: Slack notification on user login (HostWatch)` and the session line to `/usr/local/bin/hostwatch login`. Verify that after install `grep hostwatch /etc/pam.d/common-session` shows the `optional pam_exec.so` line.
- [x] 2.3 Update the comments in `config.example.ini` to name HostWatch and `/etc/hostwatch/config.ini`, keeping the placeholder webhook and all keys unchanged. Verify that the diff touches only comment lines.

## 3. Install and uninstall scripts

- [ ] 3.1 Switch `install.sh` and `uninstall.sh` to the new paths, unit name, PAM profile name, messages and `hostwatch test` hint. Verify that `bash -n` and `shellcheck` pass on both, and that a fresh install on Ubuntu 24.04 enables `hostwatch-boot.service` and creates `/etc/hostwatch/config.ini` with `-rw------- root root`.

## 4. Documentation and specs

- [x] 4.1 Update `README.md` to use "HostWatch" as the display name and `hostwatch` in all commands, paths, the journal tag (`journalctl -t hostwatch`, `-u hostwatch-boot`) and `HOSTWATCH_CONFIG`. Verify that every command in the README matches `hostwatch --help`.
- [x] 4.2 Edit the Purpose lines of `openspec/specs/service-installation/spec.md` and `openspec/specs/slack-delivery/spec.md` directly to say HostWatch, because a delta cannot change a Purpose. Verify that `openspec validate --specs --strict` passes.
- [x] 4.3 Run the name check (design D3) right after archiving: `grep -rniI "slack-heartbeat\|slack_heartbeat" --exclude-dir=.git --exclude-dir=archive .`. Verify that it prints nothing.

## 5. Final install on Ubuntu 24.04 (last step)

- [ ] 5.1 On a fresh Ubuntu 24.04 machine:
  1. Run `shellcheck install.sh uninstall.sh`.
  2. Run `sudo SLACK_WEBHOOK_URL=... ./install.sh`, then `sudo hostwatch test`.
  3. Reboot.

  Verify exactly one test message and then exactly one boot message with footer "HostWatch", `journalctl -t hostwatch` showing the deliveries, and `systemctl list-unit-files | grep -i slack` printing nothing.
- [ ] 5.2 After the reboot, log in once over SSH, once on the desktop and once on a TTY, then run `sudo -i`. Verify exactly one SSH message (with remote IP), one Graphical message and one TTY message, and nothing for sudo.
- [ ] 5.3 Run `sudo ./uninstall.sh`, then log in again. Verify that no message is sent, `grep hostwatch /etc/pam.d/common-session` prints nothing and `/etc/hostwatch` is kept. Then run `sudo ./uninstall.sh --purge` and verify `/etc/hostwatch` is removed.

## Workflow follow-up

- Archive with `/opsx:archive` after the final install. This syncs `hostwatch-config`, `service-installation` and `slack-delivery`, and retires `heartbeat-config`. Then run task 4.3.
- The archived `add-slack-heartbeat` change still lists its own Ubuntu checks as open. Group 5 covers the same ground under the new name.
