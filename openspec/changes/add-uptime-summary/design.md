# Design

## Context

HostWatch is Python 3 stdlib only, split into small pure-function modules (`timefmt.py`, `messages.py`) plus thin I/O modules (`state.py`, `config.py`) wired together in `cli.py`. `state.py` already shows the patterns this change reuses: atomic writes under `/var/lib/hostwatch` (`os.open` + `O_CREAT`/`O_TRUNC` + `fsync`, directory fsync'd too), and a `*_STATE_DIR_ENV` override for tests. `timefmt.uptime_seconds()`/`kernel_boot_time()` already give the current session's start and length from `/proc`. Every unit (`hostwatch-boot.service`, `-shutdown.service`, `-heartbeat.service`/`.timer`) runs with `ProtectSystem=strict` and a `StateDirectory=hostwatch` that is the only writable location. See proposal.md - Why/What Changes for motivation and scope.

## Goals / Non-Goals

**Goals:**
- One pure function, `uptime.today_uptime(ledger_entries, current_session, now)`, used by boot/shutdown/heartbeat alike, fully unit-testable without touching the filesystem or the clock.
- Ledger and last-alive I/O that can never turn a message failure into a notification failure: every read/write is wrapped so the caller always gets back a best-effort result plus a reason to log, never an exception.
- Reuse `state.py`'s existing atomic-write idiom rather than inventing a second one.

**Non-Goals:**
- Any accounting for suspend/hibernate (documented limitation; wall clock boot-to-shutdown only, per proposal).
- A general-purpose event store; the ledger only ever holds boot-session rows.
- Cross-process coordination beyond simple mutual exclusion for the small, infrequent writes this feature makes (boot, shutdown, heartbeat tick, last-alive tick) - no queueing, no durability guarantees beyond what fsync+rename already gives `state.py`.

## Decisions

### Ledger format and location: one JSON array, `uptime.json`
Each entry: `{"start": "<ISO 8601 UTC>", "end": "<ISO 8601 UTC>|null", "reason": "clean|reboot|unclean|null"}`. `null` end/reason means "open" (the currently running session, or a session that crashed before being closed and before any last-alive timestamp existed - treated as unclean with no estimate available).

Alternative considered: append-only line-oriented log (one JSON object per line). Rejected because pruning (retention_days) and closing-the-previous-entry both need to rewrite the last record in place, which a true append-only log does not make easier than rewriting a small JSON array does - the whole ledger is expected to stay well under a few hundred rows (90 days of reasonable reboot frequency), so "rewrite the whole file" is cheap and matches the atomic-replace pattern `state.py` already uses for `clean_shutdown`.

### Shared calculation lives in `uptime.py`, takes data not paths
`uptime.today_uptime()` takes already-loaded ledger entries (plain dicts or a small namedtuple), the current session's boot time, and "now" - no file I/O, no `datetime.now()` inside it. This is what makes the acceptance scenarios (several sessions, midnight crossing, estimated session, empty/corrupt ledger, clock moved backwards) direct unit tests: construct the input, assert the output, no fixtures or monkeypatching of the clock needed. I/O (`uptime.load_ledger()`, `uptime.record_boot()`, `uptime.close_open_entry()`, `uptime.read_last_alive()`, `uptime.touch_last_alive()`) lives in the same module but is exercised separately with `HOSTWATCH_STATE_DIR` the same way `test_state.py` already does.

### Locking: `fcntl.flock` on a dedicated lock file, short timeout, best-effort
A `uptime.lock` file (not the ledger itself) is opened and `flock`'d (`LOCK_EX`) before any read-modify-write of `uptime.json`; the ledger file itself is still replaced via temp-file-then-`os.rename` so a reader that doesn't take the lock (there is none planned, but it costs nothing) still never sees a partial write. The lock acquisition itself uses a short non-blocking retry loop (a few hundred ms budget) rather than blocking indefinitely, because nothing here may delay boot/login/shutdown beyond their existing timeouts (per the uptime-summary spec's "Ledger access never delays a notification"); if the lock can't be acquired in time, the caller logs and proceeds without updating the ledger for this run, exactly like any other ledger failure.

Alternative considered: a single atomic rename with no lock, relying on "the writer that loses the race just overwrites". Rejected: two writers (e.g. the last-alive timer and a heartbeat landing at the same tick) doing read-modify-write without a lock can race and the second writer's rename can silently discard the first writer's update (lost update, not corruption, but still wrong) - `fcntl.flock` around the read-modify-write section is a few lines and removes that class of bug entirely; corruption-by-partial-write is independently prevented by the temp-file+rename.

`fcntl` is POSIX-only but HostWatch already targets Ubuntu/systemd exclusively (PAM, `/proc`, systemd units), so this adds no new platform constraint.

### Estimating the previous session's end: last-alive timestamp, not "now"
At boot, if the previous entry is still open, it's closed using the last-alive timestamp file (if present and sane) with `reason="unclean"` and an `estimated=True` flag; if no last-alive timestamp exists at all (e.g. a crash within the first interval after install, before the timer ever ran), the entry is closed at its own start time (zero estimated duration) rather than guessed from "now" at boot, since "now" at boot is unrelated to when the crash happened. The timestamp file itself is a single small text file (epoch seconds), written via the same temp-file+rename idiom, kept deliberately tiny to limit disk wear as required by the proposal.

### First run after install: no ledger means no warning, not "unclean"
`uptime.load_ledger()` distinguishes "file absent" (first run, or freshly pruned to empty) from "file present but unparseable" (corrupt) only for logging purposes - both resolve to an empty ledger for the calculation, but only the corrupt case logs a journal warning, per the uptime-summary spec. Critically, ledger absence is independent of `state.py`'s existing `clean_shutdown` marker, which already handles the install-time "no false unclean warning" case (`install.sh` seeds it on first install) - this change does not touch that marker or its logic, it only adds the separate uptime ledger.

### Config: new `[uptime]` section, validated the same way `[heartbeat]` is
`config.Config` gains three new raw string fields (`uptime_daily_summary`, `uptime_last_alive_interval`, `uptime_retention_days`) with string defaults, validated lazily by a new `config.uptime_settings(cfg)` - mirroring `heartbeat_settings()`/`login_settings()` so a typo in `[uptime]` can't take down boot/login/shutdown, only the daily-summary line (and, for the interval, the timer's own re-applied schedule at next `install.sh` run).

### Boot message's optional field: config-gated the same as the others
"Uptime today before this boot" is controlled by the same `daily_summary_enabled` flag as the other two messages (the proposal's "optionally" refers to the field being new/omittable when there's no prior session or the summary is off, not a separate toggle) - this avoids a fourth config key no one asked for.

### Last-alive timer unit: mirrors `hostwatch-heartbeat.timer`/`.service`
`hostwatch-last-alive.timer` (`OnActiveSec=`/`OnUnitActiveSec=` from `[uptime] last_alive_interval_minutes`, applied via a drop-in exactly like the heartbeat timer's `HEARTBEAT_DROPIN`) and `hostwatch-last-alive.service` (`Type=oneshot`, `ExecStart=/usr/local/bin/hostwatch last-alive`, same hardening flags: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `Nice=10`, `IOSchedulingClass=idle`). `install.sh` installs/enables/verifies it with the same `systemctl show -p TimersMonotonic`/`list-timers` check already used for the heartbeat timer (factored so both checks share one shell function rather than duplicating the warning block).

## Risks / Trade-offs

- **[Risk]** A host that reboots very frequently (e.g. flaky hardware) grows the ledger beyond the expected small size before the next prune runs (pruning happens at boot). → Mitigation: pruning also runs opportunistically whenever the ledger is rewritten for another reason (closing an entry), not only at boot; the entry format is small (a few dozen bytes each) so even a few hundred unpruned rows cost nothing material.
- **[Risk]** `flock` contention under real concurrency (last-alive timer tick lands exactly when a heartbeat or shutdown is also writing) could occasionally make one writer skip its update for that run if the short timeout is hit. → Mitigation: this is an accepted trade-off per the spec ("ledger access never delays a notification" takes priority over always recording); a missed single tick is invisible to "uptime today" since the next successful write (heartbeat, next timer tick, or shutdown) catches up, and it never corrupts the file.
- **[Risk]** Clock/timezone changes between a session's recorded start and "now" could otherwise produce a negative or absurd duration. → Mitigation: `uptime.today_uptime()` clamps every session's contribution to `[0, now - session_start]` and drops a session whose own `end < start` instead of propagating a negative number (covered by the "clock moved backwards" unit test required by the proposal).
- **[Trade-off]** JSON ledger instead of an append-only log means every write rewrites the whole (small) file rather than appending a line. Chosen deliberately (see Decisions) because close/prune both need in-place edits anyway; revisit only if the ledger's expected size assumption (90 days, normal reboot cadence) stops holding for some deployment.

## Migration Plan

- New files only (`uptime.json`, the last-alive timestamp file, the new timer/service units, the new `[uptime]` config section with defaults): nothing existing changes shape, so there is no data migration.
- `install.sh` creates `/var/lib/hostwatch` exactly as it does today (unchanged branch) before anything in this change touches it; the new ledger and timestamp files simply appear in that existing directory on first boot/heartbeat/timer tick after upgrade.
- Rollback is "reinstall the previous version and run `uninstall.sh`'s last-alive-timer removal manually, or just stop/disable `hostwatch-last-alive.timer`" - the ledger files are inert to older code (never read by it), so no cleanup is required for a safe rollback; they are only removed if the admin opts into ledger removal during a real uninstall.
- Existing hosts that upgrade in place: the first boot after upgrading install.sh has no prior ledger, which is exactly the already-specified "first run after install" case (empty ledger, no false warning) - no special-cased upgrade path needed.
