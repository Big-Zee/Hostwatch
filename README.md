# HostWatch
Linux host monitoring and notifier

Posts to a Slack channel (through an incoming webhook) when the PC has booted, when it shuts down or reboots, when someone logs in, and as a regular heartbeat while it runs.

Every message has the same shape:
- **Header:** starts with the machine, for example `🖥️ office-pc · Boot`, or `🖥️ Office PC (office-pc) · Rebooting` when a `machine_name` is set.
- **Push preview:** the plain-text fallback that phones show starts with the same label, for example `office-pc · Booted at 2026-10-11 12:01:33 CEST`.
- **Fields:** the event's own fields, then:
  - **Local IP**: addresses of active interfaces (IPv4; IPv6 optional), shown as `interface: address`. Loopback and Docker/virtual interfaces are left out, and the addresses are read from the machine itself.
  - **Users**: who is logged in right now (see [Using HostWatch on several machines](#using-hostwatch-on-several-machines)).

Event-specific fields:
- **Boot** (`· Boot`): time and kernel boot time. If the previous shutdown was not clean, the message starts with *Previous shutdown was not clean (power loss or crash?)*.
- **Shutdown** (`· Shutting down` / `· Rebooting`): time and uptime, for example `up 5 h 12 min`.
- **Login** (`· Login: alice`): username, login type (Graphical, TTY or SSH), time, plus the remote IP for SSH or the terminal for TTY.
- **Heartbeat** (`· Heartbeat`, every 60 minutes by default): uptime (`up 3 h 0 min`), boot time (`since 2026-10-11 09:14 CEST`), and a table of the top 5 processes by current CPU use. Local IP shows IPv4 only. See [Heartbeat](#heartbeat).
- **Test** (`· Test`, from `hostwatch test`): time. It shows exactly how this machine appears in the channel.

The only network request HostWatch makes is the message to Slack. It is plain Python 3 with only the standard library, and is tested on Ubuntu 24.04. Boot, shutdown and login never wait noticeably for Slack. Boot and login failures are retried, then logged to the systemd journal.

## Install

1. Create an incoming webhook for your channel (Slack app settings → *Incoming Webhooks*).
2. From a checkout of this repository, run:

   ```bash
   sudo SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...' ./install.sh
   ```

   Without `SLACK_WEBHOOK_URL`, the script asks for the URL (the input is hidden). Leave it empty to edit the config later.
3. Check it works:

   ```bash
   sudo hostwatch test
   ```

4. Reboot. You get one "Rebooting" message, then one boot message, then one message per login.

`install.sh` does the following:
- copies the package to `/usr/local/lib/hostwatch/` and the command to `/usr/local/bin/hostwatch`
- installs `hostwatch-boot.service` and enables it
- installs `hostwatch-shutdown.service`, enables it and starts it, so the very next shutdown is announced
- installs `hostwatch-heartbeat.timer` / `.service`, applies `[heartbeat] interval_minutes` to the timer, and starts it
- creates `/var/lib/hostwatch/` and records a clean state, so the first boot shows no unclean-shutdown warning
- adds the login hook with `pam-auth-update`
- creates `/etc/hostwatch/config.ini` (root, mode `600`) from `config.example.ini`

Running it again updates the program and keeps your config.

## Configuration

The config file is `/etc/hostwatch/config.ini`. It holds the webhook secret, so keep it root-only and never commit it. The repository only contains `config.example.ini` with a placeholder.

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[slack]` | `webhook_url` | *(required)* | Slack incoming webhook URL |
| `[boot]` | `skip_interfaces` | `docker,br-,veth,virbr,vnet,lxc,lxd,tun,tap,cni,flannel,zt,tailscale,wg` | Interface name prefixes left out of the local IP list |
| `[boot]` | `include_ipv6` | `false` | Also list global IPv6 addresses |
| `[display]` | `timezone` | `local` | `local` or an IANA name such as `Europe/Warsaw` |
| `[display]` | `machine_name` | *(unset)* | Optional friendly name, shown as `Office PC (office-pc)`; unset means hostname only |
| `[heartbeat]` | `enabled` | `true` | `false` stops heartbeats without uninstalling (takes effect at the next run) |
| `[heartbeat]` | `interval_minutes` | `60` | Minutes between heartbeats, counted from boot (5–1440); run `install.sh` again after changing it |

Changes take effect at the next boot, shutdown or login. There is no daemon to restart.

## Using HostWatch on several machines

One Slack channel can serve any number of PCs:
1. Use the same incoming webhook on every machine (`SLACK_WEBHOOK_URL=… ./install.sh`).
2. Optionally give each machine a friendly name in `/etc/hostwatch/config.ini`:

   ```ini
   [display]
   machine_name = Office PC
   ```

**Telling machines apart.** Every message names its machine at the start of the header and at the start of the push preview, so notifications are clear without opening Slack. For example:

```
office-pc · Booted at 2026-10-11 08:01:12 CEST
Office PC (home-pc) · alice logged in via SSH from 203.0.113.7 at 2026-10-11 09:15:40 CEST
```

Without `machine_name`, the hostname alone is shown. Run `sudo hostwatch test` on a machine to see how it appears.

**The Users field** lists who is logged in when the message is sent:
- **One entry per session:** `alice · desktop`, `alice · ssh from 203.0.113.7`, `bob · tty`. A desktop session counts once, however many terminal windows are open in it. Separate sessions (desktop + SSH) are listed separately, and identical ones are combined, for example `bob · ssh from 203.0.113.9 (2 sessions)`.
- **Excluded:** the login screen, lock screen, background sessions (for example `su` or cron), sessions that are closing, and display-manager accounts (`gdm`, `gdm-greeter`, `lightdm`, `sddm`).
- **Nobody logged in:** the field says *No users logged in*. That's normal at boot without auto-login and on headless machines.
- **Where the data comes from:** systemd-logind (`loginctl`). It counts sessions rather than terminals and sees Wayland desktops that never appear in `who`. If logind can't be queried, HostWatch falls back to `who`.
- **Timing:** at login, HostWatch waits briefly (up to 3 s, in the background) for the new session to be registered, so it usually appears in the list. At shutdown, sessions that are already closing are left out.

## Heartbeat

While the PC is on, `hostwatch-heartbeat.timer` sends a heartbeat that shows the machine is alive, who is logged in and what is busy:

```
🖥️ office-pc · Heartbeat
Uptime  up 3 h 0 min          Since  2026-10-11 09:14 CEST
Local IP  enp3s0: 192.168.1.20
Users     alice · desktop
          alice · ssh from 203.0.113.7
Top processes (CPU over 1 s, % of one core)
    PID USER      CPU%  MEM%  NAME
   2412 alice     98.0   3.1  firefox
    911 root       2.0   0.4  Xorg
```

- **Schedule.** The schedule counts from boot, not the clock: the first heartbeat comes one interval after boot, then one every interval. The interval is `[heartbeat] interval_minutes` (default 60). `install.sh` writes it into a drop-in at `/etc/systemd/system/hostwatch-heartbeat.timer.d/interval.conf`.
- **Changing the interval.** Run `sudo ./install.sh` again after editing it. If the machine has been up longer than the new interval, systemd sends one heartbeat right away. A re-run with an unchanged interval sends nothing.
- **Turning it off.** Set `enabled = false`. It takes effect at the next run, with no reinstall. Boot, login and shutdown messages keep working.
- **Top processes.** HostWatch reads `/proc` twice, one second apart, so the table shows CPU use *now* (a single `ps` reading is a lifetime average).
  - CPU % is relative to one core, as in `top`, so it can go above 100 on multi-core PCs.
  - HostWatch's own process is excluded.
  - Command lines are never read or sent.
- **Local IP.** Always IPv4 only in heartbeats, even with `include_ipv6 = true`.
- **Delivery.** One attempt with a 5 s timeout. If Slack is unreachable, the failure is logged (`journalctl -t hostwatch`) and that heartbeat is dropped. Missed heartbeats are never queued or resent.
- **System-wide.** It is a root-owned system timer: it works whoever is logged in, and only administrators can stop or change it. A run takes a few seconds at low CPU and I/O priority.

## Shutdown and unclean-shutdown detection

`hostwatch-shutdown.service` does nothing while the PC runs. Its stop action (`hostwatch shutdown`) runs when systemd stops it during poweroff or reboot. The unit is ordered after `network-online.target`, and systemd stops units in reverse order, so the message goes out while the network and DNS are still up.

- **Event type.** The kind of shutdown is read from systemd's job queue: `reboot.target` means "Rebooting", and `poweroff.target`, `halt.target` or anything unknown means "Shutting down".
- **Never holds up shutdown.** HostWatch makes one delivery attempt with a 5 s timeout and no retries, and the unit is capped at 10 s (`TimeoutStopSec`). A failure is logged and shutdown carries on.
- **Only real shutdowns.** `systemctl restart`/`stop`, reinstalling and uninstalling send nothing. The stop action checks `systemctl is-system-running` and only acts when it says `stopping`.
- **Unclean shutdowns.** A crash, power loss or hard reset can't send anything. Before sending, a clean shutdown writes `/var/lib/hostwatch/clean_shutdown`. Every boot reads and removes that marker. If it is missing, the boot message carries the warning. Each crash is reported once, and two crashes in a row are both reported.

The shutdown message needs the network to be managed system-wide. A Wi-Fi connection that only exists inside a user session may already be gone when the message is sent. In that case the failure is logged and the next boot shows no warning, because the shutdown itself was clean.

## How logins are detected (PAM, not a systemd user unit)

The login hook is a `pam_exec` line added to `/etc/pam.d/common-session` by `pam-auth-update`:

```
session optional pam_exec.so quiet /usr/local/bin/hostwatch login
```

PAM was chosen over a systemd user unit for these reasons:
- **It fires once per session.** A user unit starts once per user, so an SSH login while you are already logged in on the desktop would send nothing.
- **It sees the details.** PAM provides the service (sshd, login, gdm-password…), the terminal and the SSH remote IP.
- **It works for every user** with nothing to enable per user, and it can read the root-only config.

These measures keep logins safe:
- The line is `optional`, so a missing or failing hook can never block a login.
- The hook detaches at once and sends from the background.

Only these PAM services send a message:

| PAM service | Login type |
|---|---|
| `sshd` | SSH |
| `login` | TTY |
| `gdm-password`, `gdm-autologin`, `gdm-fingerprint`, `gdm-smartcard`, `lightdm`, `lightdm-autologin`, `sddm`, `sddm-autologin` | Graphical |

Everything else (`su`, `sudo`, `cron`, `systemd-user`, the login-screen greeter) is ignored. To support another display manager, add its PAM service name to `LOGIN_SERVICES` in `src/hostwatch/cli.py`.

## Commands

```bash
hostwatch test                 # send a test message; exit status 1 if it fails
hostwatch boot                 # what the boot unit runs
hostwatch shutdown             # what the shutdown unit runs at poweroff/reboot (does nothing otherwise)
hostwatch heartbeat            # what the heartbeat timer runs (sends one heartbeat now)
hostwatch login                # what the PAM hook runs (reads PAM_* variables)

# Preview a payload without sending it (works with the example config):
hostwatch boot --dry-run --config config.example.ini
hostwatch shutdown --dry-run --config config.example.ini
hostwatch heartbeat --dry-run --config config.example.ini
PAM_TYPE=open_session PAM_SERVICE=sshd PAM_USER=alice PAM_RHOST=203.0.113.7 \
  hostwatch login --dry-run
```

`--config PATH` (or the `HOSTWATCH_CONFIG` environment variable) uses a different config file. From a checkout, run `bin/hostwatch` instead of `hostwatch`.

## Troubleshooting

```bash
journalctl -u hostwatch-boot              # the boot unit
journalctl -b -1 -u hostwatch-shutdown    # the shutdown unit, previous boot
journalctl -t hostwatch                   # all HostWatch log entries
journalctl -u hostwatch-heartbeat         # heartbeat runs
systemctl list-timers hostwatch-heartbeat.timer   # when the next heartbeat is due
systemctl status hostwatch-boot hostwatch-shutdown   # the shutdown unit should be "active (exited)"
grep hostwatch /etc/pam.d/common-session
```

Common log messages:
- `webhook not configured`: set `webhook_url` in the config.
- `Slack rejected the message (HTTP 404)`: the webhook was revoked or mistyped.
- `giving up after N attempt(s)`: the network or Slack was unreachable.

- `previous shutdown was not clean`: logged at boot when the clean-shutdown marker was missing.
- `not a system shutdown, skipping`: the shutdown unit was stopped while the system kept running (restart, reinstall, uninstall).

- `heartbeat: disabled in config, skipping`: `[heartbeat] enabled = false`.
- `[heartbeat] interval_minutes must be a whole number from 5 to 1440`: fix the value. `install.sh` refuses to continue until it is valid.

At boot, the service retries for up to about 2.5 minutes in the background. At shutdown and for heartbeats, it tries once.

## Uninstall

```bash
sudo ./uninstall.sh            # keeps /etc/hostwatch; removes /var/lib/hostwatch
sudo ./uninstall.sh --purge    # also removes the config
```

## Development

```bash
python3 -m unittest discover -s tests -t .
```
