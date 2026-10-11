# Design

## Context

For motivation see proposal.md (Why); for behavior see `specs/`. Already in place:
- `messages.build()`: the shared header, fallback, fields and footer, plus an optional notice.
- `cli._identity(cfg)`: machine label, local addresses and users.
- `sessions.logged_in_users()`: logind with a `who` fallback.
- `netinfo.local_addresses(skip, include_ipv6)`: returns `(iface, addr)` pairs.
- `timefmt.uptime_seconds()`, `format_uptime()` and `kernel_boot_time()`.
- `slack.post(..., delays=(), timeout=...)`: a single attempt when there are no delays.
- Existing units use `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` and `NoNewPrivileges`, with `SyslogIdentifier=hostwatch`.

## Goals / Non-Goals

**Goals:**
- A boot-relative, configurable, quiet-on-failure heartbeat that reuses the shared format.
- CPU figures that reflect *now*, measured cheaply with the stdlib only.

**Non-Goals:**
- Catch-up or backlog of missed heartbeats.
- Disk, temperature or network statistics.
- Changing the address rules for other message types.

## Decisions

### D1. Timer + oneshot service, interval through an installer-written drop-in
`systemd/hostwatch-heartbeat.timer`:
```ini
[Unit]
Description=Periodic HostWatch heartbeat
[Timer]
OnBootSec=60min
OnUnitActiveSec=60min
AccuracySec=1min
[Install]
WantedBy=timers.target
```
`systemd/hostwatch-heartbeat.service`:
```ini
[Unit]
Description=Slack heartbeat with uptime, users and top processes (HostWatch)
Wants=network-online.target
After=network-online.target nss-lookup.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/hostwatch heartbeat
TimeoutStartSec=30
Nice=10
IOSchedulingClass=idle
SyslogIdentifier=hostwatch
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
```
The service has no `[Install]` section, because the timer starts it.

**How the installer applies the interval**
1. It runs `hostwatch heartbeat-interval`, a hidden admin helper that prints the validated minutes or exits 1 with an error naming the setting.
2. It writes `/etc/systemd/system/hostwatch-heartbeat.timer.d/interval.conf`. The empty assignments reset the list values from the unit file before setting the new ones:
   ```ini
   [Timer]
   OnBootSec=
   OnBootSec=<N>min
   OnUnitActiveSec=
   OnUnitActiveSec=<N>min
   ```
3. It runs `daemon-reload` and `systemctl enable --now hostwatch-heartbeat.timer`. It restarts the timer **only if the drop-in content changed**.

A timer whose `OnBootSec` lies in the past fires as soon as it starts. So on a host whose uptime is already longer than the interval, a first install or an interval change sends one heartbeat right away. That is acceptable and documented. An unchanged re-run never restarts the timer, so it never sends anything.

**Why a drop-in.** The unit files stay pristine copies from the repo, and the interval stays in `config.ini` where the user edits it.

**Alternatives considered:**
- `sed` on the installed unit fights reinstalls.
- A long-running Python loop is a daemon, and timers are what systemd is for.
- `OnCalendar` follows the wall clock, which the request rules out.

### D2. Turning it off and invalid settings are checked at run time, by the heartbeat only
- **Where the settings are read.** `config.load()` reads `[heartbeat] enabled` and `interval_minutes` as raw strings into `Config`. A small helper, `config.heartbeat_settings(cfg)`, returns `(enabled: bool, interval: int)` and raises `ConfigError` naming the setting and the allowed range (5–1440).
- **Who calls the helper.** Only `hostwatch heartbeat` and `hostwatch heartbeat-interval` call it. A typo in the heartbeat section therefore can't silence boot, login or shutdown messages, which keep using `config.load()` as before.
- **When it's disabled.** `hostwatch heartbeat` logs `heartbeat: disabled in config, skipping` and exits 0. The timer keeps ticking, so turning it back on needs no reinstall.

### D3. CPU sampling from `/proc` (`src/hostwatch/processes.py`)
**Why `/proc` rather than `top -b -n 2 -d 1`:**
- `top`'s batch output depends on version, locale and the user's `~/.toprc`.
- It needs column parsing, and names get truncated unpredictably.
- `/proc` is stable, structured and stdlib-only.

A single `ps` reading is ruled out by the request, because it shows the lifetime average.

**Algorithm**
1. Snapshot every `/proc/<pid>/stat` with `utime + stime` and a monotonic timestamp.
2. Sleep `SAMPLE_SECONDS = 1.0`, then snapshot again.
3. For each PID present in both snapshots: `cpu% = Δticks / (Δwall × CLK_TCK) × 100`. That is percent of one core, as `top` shows it, so it can exceed 100 on multi-core machines.
4. Parse the stat line after the last `)`, because `comm` may contain spaces or parentheses. `utime` and `stime` are fields 14 and 15.
5. `mem% = rss_pages × page_size / MemTotal × 100`, using `/proc/<pid>/statm` and `/proc/meminfo`.
6. Read the name from `/proc/<pid>/comm` and the user from the real UID on the `Uid:` line of `/proc/<pid>/status`, resolved with `pwd`. An unknown UID shows the number.
7. Exclude `os.getpid()`, the HostWatch sampler itself. Processes that appear or exit between the snapshots are skipped, and so are unreadable entries (`OSError`).
8. Sort by CPU %, then memory %, both descending, and take the top 5.

**Table:** a full-width section headed `*Top processes* (CPU over 1 s)`, then a code block:
```
    PID USER     CPU%  MEM%  NAME
   2412 alice    98.0   3.1  firefox
    911 root      2.0   0.4  Xorg
```
- Fixed widths are about 44 characters, which fits a phone in portrait.
- User names are truncated to 8 characters and names to 15, with a `+` marking truncation, as `ps` does.
- If no process could be sampled, the block says `(no process data)`.

### D4. Message and builder changes
- `messages.build(..., sections=None)` appends each `(title, mrkdwn)` as a full-width section after the fields and before the footer.
- `heartbeat_message(machine, time_str, uptime_str, since_str, local_ips, users, top_table)`:
  - event `Heartbeat`
  - fields Uptime and Since, then Local IP and Users
  - section Top processes
  - fallback `<label> · Alive, up 3 h 0 min (since 2026-10-11 09:14 CEST)`
- `timefmt.format_time(moment, tz, seconds=True)`. With `seconds=False` the format is `%Y-%m-%d %H:%M %Z`, which is used for Since.
- **IPv4 only.** The heartbeat calls `netinfo.local_addresses(cfg.skip_interfaces, include_ipv6=False)` whatever `cfg.include_ipv6` says. `_identity()` gains an `include_ipv6` override for this.

### D5. Delivery
`slack.HEARTBEAT_TIMEOUT = 5`. `_deliver(..., delays=(), timeout=5)` makes one attempt. A failure is logged through `slack.post`, which already logs to the journal with ident `hostwatch`. Nothing is persisted, so nothing can be resent.

**Run time:** about 1 s of sampling, plus up to about 2 s each for `loginctl`/`ip` (normally milliseconds), plus up to 5 s HTTP. That is well under `TimeoutStartSec=30`.

### D6. System-wide and protected
- The units are root-owned system units in `/etc/systemd/system`, and the service runs as root.
- polkit's default policy for `org.freedesktop.systemd1.manage-units` requires administrator authentication. Non-admin users therefore can't stop, disable or mask it, and they can't edit root-owned files or the 600 config.
- No per-user setup exists or is needed.

## Risks / Trade-offs

- [Up to 24 messages per day per machine is noisy] → The interval is configurable (up to 1440 minutes) and the heartbeat can be turned off.
- [A first install, or an interval change, on a long-running host sends an immediate heartbeat] → Documented. Unchanged re-runs send nothing.
- [The 1 s sample misses short spikes] → Accepted: the heartbeat is a snapshot. Two seconds would double the run time for little gain.
- [The CPU % of one core can exceed 100 and may surprise users who expect whole-machine figures] → The table header and README say "% of one core, as in top".
- [Reading `/proc` of every process as root] → It is read-only. Only the name, owner and counters are shown. Command lines are never read or sent, so no arguments or secrets leak into Slack.
