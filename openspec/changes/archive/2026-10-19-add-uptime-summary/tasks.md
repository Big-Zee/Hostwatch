# Tasks

## 1. Shared uptime-today calculation (`src/hostwatch/uptime.py`)

- [x] 1.1 Define the ledger entry shape (start, end, reason, estimated) and a pure `today_uptime(entries, current_session_start, now)` function returning the total seconds, session count and whether any counted session is estimated; verify with `tests/test_uptime.py` covering: several sessions in a day, a session crossing midnight (clipped to 00:00), an estimated session after power loss, an empty ledger, and a clock moved backwards (negative/absurd durations excluded, never produced)
- [x] 1.2 Add `format_uptime_today(seconds, session_count, estimated)` producing `"5 h 42 min (2 sessions)"` / `"~5 h 40 min (2 sessions)"`; verify with unit tests for the exact and estimated cases
- [x] 1.3 Add a corrupt-ledger-input unit test: feeding `today_uptime`/the loader malformed entries degrades to treating them as absent rather than raising, verified by a dedicated test case

## 2. Ledger and last-alive file I/O

- [x] 2.1 Implement `load_ledger(path)` reading the JSON array, returning `[]` and a flag distinguishing "absent" from "corrupt" on any `OSError`/`ValueError`; verify with tests using `HOSTWATCH_STATE_DIR` (mirroring `test_state.py`) for: missing file, empty file, valid file, corrupt JSON
- [x] 2.2 Implement a short-timeout `fcntl.flock`-based lock helper (`uptime.lock` file, non-blocking retry within a bounded budget) wrapping a read-modify-write of the ledger via temp-file-then-`os.rename` (same idiom as `state.mark_clean`); verify with a test that two sequential writers both land cleanly and a test that lock acquisition failure is reported rather than raised
- [x] 2.3 Implement `record_boot(path, now)` appending an open entry, and `close_open_entry(path, end_time, reason, estimated=False)` closing the most recent open entry if any; verify with tests for: no open entry (no-op), one open entry closed correctly, already-closed ledger left unchanged
- [x] 2.4 Implement `prune(entries, retention_days, now)` dropping entries older than the cutoff while always keeping any still-open entry; wire it into the write path used by `record_boot`/`close_open_entry` so pruning happens opportunistically on every ledger rewrite; verify with a unit test mixing old, recent and open entries
- [x] 2.5 Implement `read_last_alive(path)` and `touch_last_alive(path, now)` using the same small-file atomic temp-file+rename write as the clean-shutdown marker; verify with tests for missing file, valid timestamp, and corrupt/unreadable content treated as absent
- [x] 2.6 Wrap every public ledger/last-alive function used from `cli.py` so a failure returns a sentinel plus a log-worthy reason instead of raising, matching the "never delay or fail a notification" requirement; verify with a test that simulates a write failure (e.g. unwritable state dir) and confirms no exception escapes

## 3. Configuration (`src/hostwatch/config.py`)

- [x] 3.1 Add `[uptime]` fields to `Config` (`uptime_daily_summary`, `uptime_last_alive_interval`, `uptime_retention_days`) with defaults `true`, `5`, `90`, loaded the same way `[heartbeat]` fields are; verify with a `test_config.py` case asserting the documented defaults when `[uptime]` is absent
- [x] 3.2 Add `uptime_settings(cfg)` validating `daily_summary_enabled` as a boolean, `last_alive_interval_minutes` as a whole number 1-60, and `retention_days` as a whole number >= 1, raising `ConfigError` naming the bad setting; verify with tests for each invalid case (non-boolean, non-numeric interval, zero retention) and the valid-defaults case
- [x] 3.3 Add the new `[uptime]` keys with comments and defaults to `config.example.ini`; verify `config.missing_settings()` reports them for an existing config that predates this change

## 4. CLI integration (`src/hostwatch/cli.py`, `bin/hostwatch`)

- [x] 4.1 In `run_boot`: after judging the previous shutdown, close any open ledger entry using the last-alive timestamp (reason "unclean", estimated) when the shutdown was not clean, else leave ledger closing to `run_shutdown`'s own close; then record the new boot entry and prune; compute "uptime today before this boot" when `daily_summary_enabled`; verify with a `test_cli.py` case simulating a crash-then-boot sequence and asserting the ledger is closed with an estimate and the new entry is open
- [x] 4.2 In `run_shutdown`: when a real shutdown is detected and the clean marker is recorded, also close the open ledger entry with the real end time and reason (clean shutdown/reboot) before delivery; compute uptime-today including the ending session; verify with a test asserting the ledger entry is closed and the message includes the field
- [x] 4.3 In `run_heartbeat`: refresh the last-alive timestamp and compute uptime-today including the running session, passing it to `messages.heartbeat_message`; verify with a test asserting both the timestamp update and the new field's presence
- [x] 4.4 Add `run_last_alive(args)`: load config (webhook not required), check `daily_summary_enabled` is irrelevant to this command (it must always touch the timestamp so a later-enabled summary isn't missing data), and call `touch_last_alive`; verify with a test asserting the timestamp file's mtime/content advances and that a failure is logged, not raised
- [x] 4.5 Wire `last-alive` as a new hidden subcommand in `build_parser()`/`main()`, parallel to `heartbeat-interval`; verify with `hostwatch last-alive --config <test config>` exiting 0 and updating the timestamp file
- [x] 4.6 Guard every new ledger/last-alive call site with the existing `try/except Exception` + `_log_unexpected` pattern already used around `run_boot`/`run_shutdown`/`run_heartbeat`, so a bug in the new code cannot fail the unit; verify with a test that an injected ledger exception still lets the notification go out without the daily-summary field

## 5. Message content (`src/hostwatch/messages.py`)

- [x] 5.1 Add an optional uptime-today parameter to `shutdown_message()` and include it as a field when present; verify with `test_messages.py` cases for present/absent
- [x] 5.2 Add an optional uptime-today parameter to `heartbeat_message()` and include it as a field when present; verify with `test_messages.py` cases for present/absent
- [x] 5.3 Add an optional "Uptime today before this boot" parameter to `boot_message()`, included only when given; verify with `test_messages.py` cases for present/absent and for "no prior session today" (field omitted)

## 6. systemd units

- [x] 6.1 Add `systemd/hostwatch-last-alive.service` (oneshot, `ExecStart=/usr/local/bin/hostwatch last-alive`, same hardening flags as `hostwatch-heartbeat.service`) and `systemd/hostwatch-last-alive.timer` (`OnActiveSec=`/`OnUnitActiveSec=` placeholders overridden by install.sh's drop-in, `AccuracySec=1min`); verify by running `systemd-analyze verify` on both files (or, if unavailable in the dev environment, a manual review against `hostwatch-heartbeat.{service,timer}`)

## 7. Installer and uninstaller

- [x] 7.1 In `install.sh`: install the two new unit files, generate a `hostwatch-last-alive.timer.d/interval.conf` drop-in from `[uptime] last_alive_interval_minutes` (factor the "generate drop-in + enable/restart + verify next-run" logic already used for the heartbeat timer into a shared shell function used by both timers); verify by running install.sh in a test environment (or VM) and checking `systemctl list-timers hostwatch-last-alive.timer` shows a next run
- [x] 7.2 In `install.sh`: validate the new `[uptime]` settings the same way `interval_minutes` is validated today (fail with a clear message naming the bad setting before touching any timer); verify with a manual run using an invalid `last_alive_interval_minutes` and confirming install.sh exits non-zero without changing units
- [x] 7.3 In `uninstall.sh`: stop/disable/remove `hostwatch-last-alive.timer`/`.service` and its drop-in directory, alongside the existing heartbeat removal; verify by running uninstall.sh and confirming no last-alive unit or enablement link remains
- [x] 7.4 In `uninstall.sh`: before removing `/var/lib/hostwatch` and `$LIB_DIR`, ask (when interactive) whether to also delete the boot-session ledger specifically, defaulting to "keep" for `--yes`-style/non-interactive runs, and keep the rest of `/var/lib/hostwatch` removal as today; verify with a manual interactive run (answer yes) and a non-interactive run, checking the ledger file's presence afterward in each case

## 8. Documentation

- [x] 8.1 Document the new `[uptime]` config keys, the last-alive timer, the ledger location/permissions, and the suspend/hibernate wall-clock limitation in `README.md`; verify by reading the updated section against the proposal's acceptance criteria
- [x] 8.2 Update any install notes referencing the heartbeat timer verification step to also mention the last-alive timer; verify by grepping the docs for "heartbeat" references that should now also cover "last-alive"

## 9. End-to-end verification

- [x] 9.1 Run the full test suite (`python -m pytest` or the project's existing test runner) and confirm all new and existing tests pass
- [x] 9.2 Manually walk the proposal's acceptance scenarios in a disposable VM or container: boot/reboot/boot/heartbeat sequence showing ~3 h across 2 sessions; shutdown message including the ending session; a session crossing midnight counting only the post-midnight portion; a hard power-cut-and-reboot showing an estimated (`~`) total with the existing unclean-shutdown warning; and a corrupted ledger or unreachable Slack webhook still letting boot/login/shutdown/heartbeat complete with the failure logged to the journal
