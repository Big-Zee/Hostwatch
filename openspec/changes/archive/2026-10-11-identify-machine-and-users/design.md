# Design

## Context

For motivation see proposal.md (Why); for behavior see `specs/`. Today `messages.py` has four builders (`boot_message`, `shutdown_message`, `login_message`, `test_message`). They share a private `_payload(header, fields, fallback, notice)` and `_local_ips()`, but each builds its own header and fallback wording. Only boot and shutdown collect local IPs (`netinfo.local_addresses`). Nothing collects sessions. The login hook runs in a detached child started from `pam_exec` and sends a fixed dict with two retries. The boot command rebuilds its payload on every retry through a closure.

## Goals / Non-Goals

**Goals:**
- One builder owns the header, the fallback prefix, the field order and the Local IP / Users fields. Event code only supplies the event name, its own fields and a summary.
- A reliable session list on Ubuntu 24.04 desktops and headless hosts, with no new dependencies.

**Non-Goals:**
- A heartbeat message, per-machine channels, a dashboard.
- Showing idle time, seat or login time per session.

## Decisions

### D1. Session source: systemd-logind (`loginctl`) first, `who` as fallback
| | `loginctl` (logind) | `who` (utmp) |
|---|---|---|
| Unit of data | One record per **session**, so terminals inside a desktop add nothing | One record per **terminal line** written to utmp. Desktop terminals may or may not add lines, depending on the emulator |
| Wayland desktops | Listed (`Type=wayland`) | Often **missing**. GNOME on Wayland does not write a utmp entry for the session |
| Session type | `Type` (x11/wayland/tty), `Remote`, `Service` (sshd) | Has to be guessed from the line name (`pts/N`, `ttyN`, `:0`) and the host column |
| Greeter / background | `Class` (greeter, lock-screen, background, manager, user) and `State` (active, online, closing) | Not available; only account names can be filtered |
| Remote IP | `RemoteHost` | Host column, which may be a reverse-DNS name if `UseDNS` is on |
| Availability | Every systemd system, including Ubuntu | Also universal; reads `/var/run/utmp` |

logind is authoritative, gives the deduplication the spec asks for, and is the only one that sees Wayland desktops reliably. `who` remains the fallback for systems where logind can't be queried, for example a container without systemd-logind or when `loginctl` times out.

**How it's queried**
1. `loginctl list-sessions --no-legend` returns the session IDs (first column).
2. One call to `loginctl show-session <id…> -p Id -p Name -p Type -p Class -p State -p Remote -p RemoteHost -p Service -p TTY` returns the properties. The records are separated by blank lines.

Each call has a 2 s timeout. `show-session -p` is used rather than `list-sessions --output=json`, because the JSON columns have changed across systemd versions while `show-session` properties are stable.

### D2. Classification, filtering and dedup (`src/hostwatch/sessions.py`)
**logind path**
- Keep a session only if `Class=user` and `State` is `active` or `online`, and the `Name` is not on the excluded-account list: `gdm`, `gdm-greeter`, any name starting with `gdm-greeter-`, `lightdm`, `sddm`, `nobody`.
- Type:
  - `x11`, `wayland` or `mir` → `desktop`
  - `Remote=yes` or `Service=sshd` → `ssh`, with `RemoteHost`
  - any other `tty` → `tty`
  - anything else → `tty`

**who path**
- Read each line as `user line … (host)`.
  - Host is `:N`, or the line is `seat0` / `:N` → `desktop`.
  - Line is `pts/N` with a host that is not `:N` → `ssh` with that host.
  - Line is `ttyN` → `tty`.
  - `pts/N` without a host is a terminal inside a desktop → dropped, which gives the same dedup as logind for that case.
- The same account exclusions apply.

**Dedup (both paths)**
- Group by `(user, type, remote)`.
- Keep first-seen order, sorted by user and then type so the output is stable.
- A count above 1 renders as `(2 sessions)`.

**Rendering**, one entry per line, for example:
```
alice · desktop
alice · ssh from 203.0.113.7
bob · ssh from 203.0.113.9 (2 sessions)
```
With nothing to show, the field reads `_No users logged in_`.

**Failure handling**
- If `loginctl` exits non-zero, times out or is missing, `who` is used.
- If `who` also fails, the list is empty and the result is logged once as a warning.
- No exception reaches the caller.

### D3. One builder (`messages.build`)
```python
def build(machine, event, fields, summary, local_ips, users, notice=None) -> dict
```
- **Machine label:** `machine_label(hostname, machine_name)` returns `"Office PC (office-pc)"`, or `"office-pc"` when the name is unset, empty or equal to the hostname.
- **Header:** `:desktop_computer: <label> · <event>`, trimmed to Slack's 150-character limit. Slack renders the shortcode as 🖥️, and an ASCII shortcode avoids encoding surprises. Event names are `Boot`, `Shutting down`, `Rebooting`, `Login: <user>` and `Test`. The old per-event emoji headers are dropped, as the spec requires the machine first.
- **Fallback:** `<label> · <summary>`. The summary starts with a capital letter:

  | Event | Summary |
  |---|---|
  | Boot | `Booted at <time>` (+ ` – previous shutdown was not clean`) |
  | Shutdown | `Shutting down at <time> (up 5 h 12 min)` / `Rebooting at …` |
  | Login | `alice logged in via SSH from 203.0.113.7 at <time>` |
  | Test | `Test message at <time>` |

  The fallback is plain text and is not escaped. Block text is mrkdwn-escaped as before.
- **Fields:** the event's fields, then `Local IP`, then `Users`. Every type stays within Slack's 10-field limit (login has the most: User, Type, Time, Remote IP or Terminal, Local IP, Users = 6).
- **Notice and footer:** the boot warning keeps using the optional notice section, and the footer stays `HostWatch`.

The four public builders become thin wrappers that pass event-specific parts to `build`, so the CLI changes stay small. The "Host" and "Event" fields are dropped, because the header carries both.

### D4. Collecting IPs and users in every command
`cli.py` gains a helper `_identity(cfg)` that returns `(label, local_ips, users)`. Every command calls it when building its payload:
- **boot:** inside the existing per-attempt closure, so late network or sessions are picked up.
- **shutdown:** once, inside its 10 s budget. `loginctl` calls are capped at 2 s each, and the usual cost is milliseconds.
- **login:** the payload becomes a closure, rebuilt per attempt like boot. Before the first build, the detached child waits up to 3 s, polling every 0.5 s, for logind to show a session for `PAM_USER` (and, for SSH, `PAM_RHOST`). Then the new session usually appears in the Users list. `pam_systemd` may register the session after our hook starts, because both sit in `common-session`. If it never appears, the message is sent anyway; the User field already names the person logging in.
- **test:** once.

Dry runs collect everything the same way. Collecting is read-only.

### D5. `machine_name` setting
- Read from `[display] machine_name`, stripped. Empty means unset, so no validation is needed.
- Stored on `Config` as `machine_name: str = ""`.
- Documented in `config.example.ini` as a commented-out example, so the default stays "hostname only".

## Risks / Trade-offs

- [Message text changes for every type] → Intended by the request. The README notes the new format.
- [A session list collected at shutdown may already be partly closing] → Closing sessions are excluded, so the list may be shorter or say "No users logged in" when sessions end first. Accepted: the message is still informative, and the spec allows it.
- [The login wait of up to 3 s happens in the detached child, so login itself is not delayed] → The PAM hook still returns at once (unchanged detach).
- [`RemoteHost` may be a hostname instead of an IP when sshd `UseDNS yes`] → It is shown as given. Ubuntu's default is `UseDNS no`.
- [The excluded-account list may miss an exotic display manager's account] → `Class=greeter` filtering already removes greeter sessions on logind, and the name list is a second guard. The list is easy to extend in `sessions.py`.
