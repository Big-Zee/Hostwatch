# Tasks

## 1. Building blocks

- [x] 1.1 Add `src/hostwatch/processes.py` (design D3): a `/proc` snapshot (utime+stime and monotonic time), `top_processes(n=5, sample=1.0, proc_root="/proc", sleep=..., clock=..., own_pid=...)` returning rows (pid, user, cpu%, mem%, name), and `format_table(rows)` producing the fixed-width block with `+` truncation. Verify with `tests/test_processes.py` using a fake `/proc` tree in a temp dir across two snapshots:
  - an idle-then-busy process ranks first with about 100 %
  - the own PID is excluded
  - processes exiting or appearing between snapshots are skipped
  - a `comm` containing spaces and parentheses parses correctly
  - mem % comes from statm and meminfo
  - truncation and alignment are correct, and the empty case reads "(no process data)"
- [x] 1.2 Add `seconds=False` support to `timefmt.format_time` (`2026-10-11 09:14 CEST`). Verify with a test that also checks the existing seconds format is unchanged.
- [x] 1.3 Add the heartbeat settings to `config.py`: raw `heartbeat_enabled` and `heartbeat_interval` on `Config`, plus `heartbeat_settings(cfg)` validating the boolean and the 5–1440 integer and raising `ConfigError` with the setting name (design D2). Add a documented `[heartbeat]` section to `config.example.ini`. Verify with tests:
  - the defaults are (True, 60)
  - valid values parse
  - `interval_minutes` of 1, 1441 or `hourly`, and a non-boolean `enabled`, each raise naming the setting
  - `config.load()` itself still succeeds with an invalid heartbeat section, so boot and login are unaffected

## 2. Message and command

- [x] 2.1 Add optional full-width `sections` to `messages.build()` and a `heartbeat_message()` builder (design D4: event `Heartbeat`, fields Uptime/Since/Local IP/Users, Top processes section, fallback `<label> · Alive, up … (since …)`). Verify with message tests: header, fallback prefix, field order, the section placed after the fields and before the footer, and the code block intact. Existing builders must be unchanged.
- [x] 2.2 Add `hostwatch heartbeat` to `cli.py`:
  - when disabled, log and exit 0
  - an invalid heartbeat setting logs a config error and sends nothing
  - collect identity with IPv4 only, uptime, boot time without seconds and the top-5 table
  - one delivery attempt with `HEARTBEAT_TIMEOUT = 5`
  - always exit 0

  Also add the hidden `hostwatch heartbeat-interval` (prints minutes, or exits 1 with the error). Verify with CLI tests: disabled sends nothing; an invalid interval sends nothing and logs the setting name; IPv6 never appears even with `include_ipv6 = true`; `post` gets `delays=()` and `timeout=5`; a failed post exits 0; `--dry-run` prints the payload; `heartbeat-interval` prints 60 by default and exits 1 on 1.

## 3. Units and scripts

- [ ] 3.1 Add `systemd/hostwatch-heartbeat.timer` and `systemd/hostwatch-heartbeat.service` as in design D1. Verify `systemd-analyze verify` for both on Ubuntu after install.
- [ ] 3.2 Update `install.sh`:
  - install both units
  - get the interval from `hostwatch heartbeat-interval`, aborting with its message on error
  - write the `interval.conf` drop-in
  - run `daemon-reload` and `enable --now` the timer
  - restart the timer only when the drop-in changed

  Verify that `bash -n` passes, and in the stub sandbox that the drop-in has the configured minutes, that an unchanged re-run doesn't call `restart`, that a changed interval does, and that an invalid interval aborts. On Ubuntu, `systemctl list-timers hostwatch-heartbeat.timer` should show the next run.
- [ ] 3.3 Update `uninstall.sh`: `disable --now` the timer and remove both units and the `.timer.d` drop-in directory. Verify that `bash -n` passes, that the stub sandbox shows the files removed, and on Ubuntu that `systemctl list-unit-files | grep hostwatch` prints nothing.
- [x] 3.4 Update `README.md`:
  - the heartbeat message and an example
  - the schedule relative to boot
  - `[heartbeat] enabled` / `interval_minutes`, and rerunning `install.sh` after changing the interval
  - the immediate first heartbeat on long-running hosts
  - CPU % as % of one core over 1 s, IPv4 only
  - troubleshooting (`systemctl list-timers`, `journalctl -u hostwatch-heartbeat`)

  Verify that the config table matches `config.example.ini` and that the documented commands run.

## 4. Acceptance on Ubuntu 24.04 (with the final install)

- [ ] 4.1 Set `interval_minutes = 5` and run `sudo ./install.sh`, then reboot. Verify that the first heartbeat arrives about 5 minutes after boot and then every 5 minutes, with header `🖥️ <machine> · Heartbeat`, uptime, since-time, IPv4-only addresses, users and a 5-row process table.
- [ ] 4.2 Run `yes > /dev/null` in a terminal and wait for a heartbeat. Verify that `yes` tops the table at about 100 % CPU and that no `hostwatch`/`python3` sampler row appears.
- [ ] 4.3 Set `enabled = false` and wait past an interval. Verify that no heartbeat is sent and that a new SSH login still produces a login message. Set it back to true and verify heartbeats resume without reinstalling.
- [ ] 4.4 Block Slack (`iptables -I OUTPUT -p tcp --dport 443 -j REJECT`) for two intervals, then unblock. Verify that `journalctl -t hostwatch` shows the failed heartbeats and that only the next scheduled one is delivered, with no backlog.
- [ ] 4.5 As a non-admin user, run `systemctl stop hostwatch-heartbeat.timer`. Verify that it is refused or asks for an admin password, and that heartbeats continue. Also time a heartbeat run (`systemctl show -p ExecMainStartTimestamp,ExecMainExitTimestamp hostwatch-heartbeat.service`) and verify it finishes within a few seconds.

## Workflow follow-up

- Archive with `/opsx:archive` after acceptance. This syncs the new `heartbeat-notification`, plus `message-identity`, `slack-delivery`, `hostwatch-config` and `service-installation`.
