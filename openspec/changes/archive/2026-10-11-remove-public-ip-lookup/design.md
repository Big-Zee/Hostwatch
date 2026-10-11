# Design

## Context

For motivation see proposal.md (Why); for behavior see `specs/`. Today `cli.run_boot()` builds the boot payload in a closure that is called again on every delivery attempt. Each attempt does three things:
- reads local addresses with `netinfo.local_addresses()`, which runs `ip -j addr show`
- calls `netinfo.public_ip()`: an HTTPS GET with a 5 s timeout, when `public_ip` is on (the default)
- passes both to `messages.boot_message()`

The config parser reads only the keys it knows, so unknown keys are already ignored. The two settings to drop are read and validated in `config.load()` / `config.validate()`.

## Goals / Non-Goals

**Goals:**
- No network request other than the Slack webhook.
- Local address output as the spec describes: `interface: address`, one per line, "no local IP" when empty, `127.0.0.0/8` filtered.
- Old configs keep loading.

**Non-Goals:**
- No change to IPv6 handling (`include_ipv6`), login messages, the retry schedule or unit ordering.

## Decisions

### D1. Keep reading addresses from `ip -j addr show` (JSON)
The request offers two options: the standard library, or parsing `ip -4 -o addr show`. The current implementation is a third option: run `ip -j addr show` and parse it with the stdlib `json` module. I recommend keeping it. Comparison:

| | `ip -j addr show` (current) | `ip -4 -o addr show` (text) | Stdlib only (`socket` + `fcntl.ioctl`, `/sys/class/net`) |
|---|---|---|---|
| Parsing | `json.loads`; fields are named | Splits free-form text. Columns move around with labels (`enp3s0:1`), optional `brd`, and flags (`dynamic`, `noprefixroute`) | `struct` packing of `SIOCGIFADDR`; Linux ABI details in Python |
| Interface up/down | `operstate` and `flags` are in the same output | Not included. Addresses on DOWN interfaces are listed too, so a second `ip -o link` call is needed | Separate `/sys/class/net/*/operstate` reads |
| Several addresses per interface | All listed | All listed | Primary IPv4 only |
| Works with `include_ipv6` | Yes | No (`-4`) | No |
| Dependencies | iproute2, which Ubuntu always has, and `install.sh` already checks for `ip` | iproute2 | None |
| Existing code and tests | Already in place and tested with fixtures | Rewrite | Rewrite |

The JSON output is a stable interface with named fields. It gives up/down state and every address in one call, so it is the most robust option.

If `ip` is missing or fails, the code keeps today's behavior: it logs a warning and returns an empty list. The message then says "no local IP" instead of failing.

### D2. Loopback filtering by address as well as by interface
`parse_ip_json()` already skips interface `lo` and anything with the `LOOPBACK` flag. It will also drop any address where `ipaddress.ip_address(local).is_loopback` is true. That covers `127.0.0.0/8`, plus `::1` if IPv6 is on. Without this, an address such as `127.0.1.1` on a regular interface would be listed.

### D3. Removing the public-IP code
- `netinfo.py`: delete `public_ip()`, `PUBLIC_IP_TIMEOUT` and the imports that only it used (`urllib.request`, `http.client`).
- `config.py`: delete the two fields from `Config`, the `DEFAULT_*` constant, their reads in `load()` and the URL check in `validate()`. Nothing is added for the old keys. configparser already ignores keys nobody reads, and removing the `getboolean` call is exactly what stops an invalid old value from raising an error.
- `cli.py`: the boot closure only reads local addresses.
- `messages.boot_message()`: the signature becomes `(host, time_str, boot_time_str, local_ips)`. The "Public IP" field is dropped. Local addresses are rendered as `<iface>: <addr>`, escaped, joined with newlines. The empty case shows `_no local IP_`. The order of the remaining fields (Time, Host, Local IP, Kernel boot) and the fallback text are unchanged.

### D4. Keeping the acceptance grep clean
The check is `grep -ri "ipify\|public ip\|public_ip"` outside `openspec/changes/archive/`, so nothing new may contain those strings:
- The test for ignored settings uses a neutral unknown key (`retired_option = maybe`) to prove the mechanism. It doesn't name the removed key.
- README and comments do not say "no public IP". They describe what *is* shown.
- After archiving, the REMOVED requirement disappears from the main spec. The MODIFIED and ADDED requirement texts avoid the phrase.

## Risks / Trade-offs

- [The boot message no longer shows the WAN address, so a host behind changing NAT cannot be identified from outside] → Intended. The requirement is identification on the LAN.
- [A config written from the old example keeps two dead keys] → They are harmless and ignored silently. The README configuration table lists only the supported keys.
- [`ip` output format changes in a future iproute2] → JSON output is a stable interface, and parsing already tolerates missing fields with `.get`.
