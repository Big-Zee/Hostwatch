# Tasks

## 1. Building blocks

- [x] 1.1 Add `src/hostwatch/state.py` with `STATE_DIR` (`/var/lib/hostwatch`, overridable by `HOSTWATCH_STATE_DIR`), `mark_clean()` (write the marker and fsync file and directory), `consume_clean()` (return whether the marker existed, then remove it) and `peek_clean()` (no removal). Errors are logged and reported as "not clean" (consume) or ignored (mark). Verify with `tests/test_state.py` using a temp dir: mark then consume returns True, a second consume returns False, peek doesn't remove, and a missing dir is handled without an exception.
- [x] 1.2 Add uptime support: `timefmt.uptime_seconds()` (read `/proc/uptime`, None on error) and `timefmt.format_uptime(seconds)` giving `up 5 h 12 min`, `up 2 d 3 h 4 min`, `up 12 min` or `up 0 min`. Verify with tests for those cases, a fixture `/proc/uptime` and a missing file.
- [x] 1.3 Add `netinfo.shutdown_kind(run=subprocess.run)`, which returns "Rebooting" or "Shutting down" from `systemctl list-jobs --no-legend --plain` (2 s timeout): reboot/kexec/soft-reboot targets mean Rebooting, anything else or an error means Shutting down. Also add `netinfo.system_stopping(run=...)`, which is True only when `systemctl is-system-running` prints `stopping`. Verify with tests on fixture outputs (reboot.target job, poweroff.target job, empty, a command error, a timeout).

## 2. Messages and delivery

- [x] 2.1 In `messages.py`, factor out the local-IP rendering shared by boot and shutdown. Add `shutdown_message(host, event, time_str, local_ips, uptime_str)` with the D6 header, fields Event, Time, Host, Local IP and Uptime, and the fallback `my-pc is shutting down at … (up …)`. Add an `unclean_previous` flag to `boot_message` that inserts the warning section and extends the fallback. Verify with tests for both shutdown headers, the field order, the empty-IP case, the boot message with and without the warning, and the existing boot tests still passing.
- [x] 2.2 Add `SHUTDOWN_TIMEOUT = 5` to `slack.py` and let `cli._deliver` pass a per-event `timeout`. Verify with a test that a shutdown delivery calls `post` with `delays=()` and `timeout=5`, and that boot and login still use their schedules and the default timeout.

## 3. Commands

- [x] 3.1 Add the `shutdown` subcommand to `cli.py`. If `system_stopping()` is false, log "not a system shutdown, skipping" and return 0 without marking or sending, unless `--dry-run`. Otherwise call `mark_clean()`, then build and send the message (one attempt, 5 s). It always exits 0. Verify with tests: not stopping means no marker and no post; stopping means the marker is written *before* `post` is called (call-order assertion) and post is called once; a post failure still exits 0; and `shutdown --dry-run` prints a payload without writing the marker.
- [x] 3.2 In `run_boot`, call `state.consume_clean()` first, before loading the config, or `peek_clean()` for a dry run, and pass `unclean_previous = not clean` to the builder. Verify with tests: marker present gives no warning and the marker is removed; marker absent gives the warning; a config error still consumes the marker; and a dry run leaves the marker in place.

## 4. Units and scripts

- [ ] 4.1 Add `systemd/hostwatch-shutdown.service` as in design D1, and add `StateDirectory=hostwatch` to `systemd/hostwatch-boot.service`. Verify `systemd-analyze verify` for both units on Ubuntu after install.
- [ ] 4.2 Update `install.sh`:
  - install the new unit
  - `install -d -m 755 /var/lib/hostwatch` and write the marker (`: > /var/lib/hostwatch/clean_shutdown`)
  - `systemctl enable hostwatch-boot.service` (unchanged) plus `systemctl enable --now hostwatch-shutdown.service`

  Verify that `bash -n` passes, then in the stub sandbox from earlier that the marker exists after install and the enable calls are made, and on Ubuntu that `systemctl is-active hostwatch-shutdown` prints `active`.
- [ ] 4.3 Update `uninstall.sh`: `systemctl disable --now hostwatch-shutdown.service || true`, remove its unit file, and `rm -rf /var/lib/hostwatch`, before removing the program. Verify that `bash -n` passes, and on Ubuntu that uninstalling sends no Slack message and leaves no `hostwatch*` units or `/var/lib/hostwatch`.
- [x] 4.4 Update `README.md`: the shutdown message (event, fields, uptime), the unclean-shutdown warning and how it works, that a single 5 s attempt is made at shutdown, troubleshooting (`journalctl -u hostwatch-shutdown`), and the new paths in the install/uninstall lists. Verify that the documented commands match `hostwatch --help`.

## 5. Acceptance on Ubuntu 24.04 (with the final install)

- [ ] 5.1 Run `sudo poweroff`, then boot. Verify exactly one "Shutting down" message with time, host, `iface: addr` and uptime, followed by one boot message without a warning.
- [ ] 5.2 Run `sudo reboot`. Verify exactly one "Rebooting" message followed by one boot message without a warning.
- [ ] 5.3 Make Slack unreachable, for example with `sudo iptables -I OUTPUT -p tcp --dport 443 -j REJECT` or by pointing the webhook at a blackhole IP, then run `sudo poweroff` and time it. Verify that shutdown takes at most about 10 s longer than usual, `journalctl -b -1 -u hostwatch-shutdown` shows the logged failure, and the next boot has no unclean warning.
- [ ] 5.4 Hard-reset the VM (or cut power), then boot. Verify that the boot message contains "Previous shutdown was not clean (power loss or crash?)". Hard-reset again before any clean shutdown and verify the warning appears again.
- [ ] 5.5 Run `sudo systemctl restart hostwatch-shutdown` and `sudo ./install.sh` while the system is up. Verify that no message is sent.

## Workflow follow-up

- Archive with `/opsx:archive` after acceptance. This syncs `shutdown-notification` (new), `boot-notification`, `slack-delivery` and `service-installation`.
