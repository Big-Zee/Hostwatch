# Tasks

## 1. Remove the public-IP lookup

- [x] 1.1 Delete `public_ip()`, `PUBLIC_IP_TIMEOUT` and their now-unused imports from `src/hostwatch/netinfo.py`. Delete the `PublicIpTest` class from `tests/test_netinfo.py`. Verify that `python3 -m unittest discover -s tests -t .` passes and that `grep -n "urllib\|http.client" src/hostwatch/netinfo.py` prints nothing.
- [x] 1.2 Remove the two public-IP fields, their default constant, their reads in `load()` and their check in `validate()` from `src/hostwatch/config.py`. Update `tests/test_config.py`: drop the assertions about those fields, replace the bad-boolean test with one on `include_ipv6`, and add a test that a config with an unknown key holding an invalid value (`retired_option = maybe` under `[boot]`) loads without error. Verify that the config tests pass.
- [x] 1.3 Remove the two settings and their comments from `config.example.ini`, leaving every other key unchanged. Verify with `git diff config.example.ini` that only those four lines are gone.

## 2. Local addresses in the boot message

- [x] 2.1 In `netinfo.parse_ip_json()`, also skip any address that `ipaddress.ip_address(...).is_loopback` reports as loopback (design D2). Verify that a new fixture case (`127.0.1.1` on an up `enp0s8`) is excluded in `tests/test_netinfo.py`, and that the existing cases (docker, veth, down interfaces, IPv6 toggle) still pass.
- [x] 2.2 Change `messages.boot_message()` to `(host, time_str, boot_time_str, local_ips)`: drop the Public IP field, render each address as `iface: addr` on its own line, and show `_no local IP_` when the list is empty. Update `cli.run_boot()` so it no longer looks up or passes a public IP. Update `tests/test_messages.py` (typical message, two interfaces as `enp3s0: 192.168.1.20` / `wlp2s0: 192.168.1.35`, empty case) and `tests/test_cli.py` (boot dry run with no lookup mocked). Verify that all tests pass and that `python3 bin/hostwatch boot --dry-run --config config.example.ini` prints a payload with fields Time, Host, Local IP and Kernel boot only.

## 3. Documentation and name check

- [x] 3.1 Update `README.md`: the boot message description lists local IPs only, and the configuration table drops the two rows. Verify that the table matches the keys in `config.example.ini`.
- [x] 3.2 Run `grep -rniI "ipify\|public ip\|public_ip" --exclude-dir=.git --exclude-dir=archive . | grep -v openspec/changes/remove-public-ip-lookup`. Verify that it prints nothing except lines in `openspec/specs/` that this change's deltas replace or remove at archive time (`boot-notification`, `hostwatch-config`).

## 4. Acceptance on Ubuntu 24.04 (with the final install)

- [ ] 4.1 With internet access, reboot and watch outbound connections, for example with `sudo tcpdump -n 'tcp[tcpflags] & tcp-syn != 0 and not dst net 192.168.0.0/16'` or `ss -tnp | grep python`. Verify that the boot message arrives within seconds of `network-online.target`, shows the correct LAN address as `iface: addr`, and that the only outbound connection is to `hooks.slack.com`.
- [ ] 4.2 Add obsolete settings (for example from the old example config, with an invalid value) to `/etc/hostwatch/config.ini` and run `sudo hostwatch test`. Verify that the message is delivered and `journalctl -t hostwatch` shows no warning or error about them.

## Workflow follow-up

- Archive with `/opsx:archive` after acceptance. This syncs `boot-notification` and `hostwatch-config`. Then rerun the grep from 3.2 and verify it prints nothing.
