# Proposal

## Why

The PC only needs to be identified on the local network. The public-IP lookup has three problems:
- it adds a third-party dependency (`api.ipify.org` by default)
- it sends a request outside the LAN on every boot
- it adds up to a 5 s wait to each boot delivery attempt when the internet is slow or down

The webhook to Slack should be the only outbound request HostWatch makes.

## What Changes

- **Remove the public-IP lookup** completely: the lookup function, its timeout and its use when building the boot message.
- **Remove the `public_ip` and `public_ip_url` settings** from `config.example.ini` and from config parsing. An existing `/etc/hostwatch/config.ini` that still contains them keeps working: the keys are ignored silently, including invalid values.
- **The boot message no longer has a "Public IP" field.** It shows local addresses only, read from the machine itself with no network request.
- **Local address field format:** each qualifying interface is shown as `interface: address`, for example `enp3s0: 192.168.1.20`. Entries are one per line, so they read well on mobile. When nothing qualifies, the field shows "no local IP" (previously "none found").
- **Local address filtering is tightened:** loopback addresses (`127.0.0.0/8`) are skipped even when they sit on a non-loopback interface. The existing filters stay: interface must be up, loopback interface skipped, and the configurable skip prefixes (docker, br-, veth, virbr, tun, tap, …).
- The boot unit still waits for `network-online.target`. The retry schedule is unchanged, and addresses are still re-read on every attempt.
- README, tests and specs drop every mention of the public IP.

Out of scope:
- IPv6. The existing `include_ipv6` option (default off) is unchanged.
- Login messages. They do not show local addresses today and still won't.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `boot-notification`: The message content drops the public IP. Local address formatting, the empty case and loopback filtering are made explicit. The public-IP requirement is removed, and a requirement is added that gathering boot information makes no network requests.
- `hostwatch-config`: The supported settings no longer include the public-IP options. Obsolete settings in existing configs are ignored silently.

## Impact

- **Code:**
  - `src/hostwatch/netinfo.py`: `public_ip()` removed; loopback-address filter added
  - `src/hostwatch/config.py`: the two settings and their validation removed
  - `src/hostwatch/messages.py`: Public IP field removed; local IP format and empty text changed
  - `src/hostwatch/cli.py`: no lookup call
- **Tests:** `tests/test_netinfo.py`, `test_config.py`, `test_messages.py` and `test_cli.py` updated.
- **Docs:** `config.example.ini` and `README.md`.
- **Hosts:** nothing is installed yet. A config written from the old example still loads, with no error.
- **Network:** the only outbound request is the Slack webhook.
