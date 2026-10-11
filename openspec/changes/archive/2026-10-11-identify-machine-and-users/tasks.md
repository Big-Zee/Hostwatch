# Tasks

## 1. Logged-in users

- [x] 1.1 Add `src/hostwatch/sessions.py` with the logind path (design D1/D2): `list-sessions --no-legend` for IDs, then one `show-session -p …` call. Parse the blank-line-separated records, filter by `Class=user`, `State` active or online, and the excluded accounts, then classify as desktop, ssh or tty. Verify with `tests/test_sessions.py` using fixture outputs: a desktop (wayland) plus SSH session for one user, a greeter session (`gdm`, `Class=greeter`), a background `su` session, a closing session and a tty session.
- [x] 1.2 Add the `who` fallback and the shared dedup in `sessions.py`. `logged_in_users(run=…)` tries logind, falls back to `who`, and returns `[]` when both fail, with one warning. Dedup is on (user, type, remote) with counts and stable order. Verify with tests: loginctl missing or erroring falls back to `who` (`pts/0 (203.0.113.9)` becomes ssh, `pts/1` without a host is dropped, `tty3` becomes tty, `:0` becomes desktop), two identical SSH sessions collapse to a count of 2, both sources failing gives `[]`, and timeouts are honoured (2 s).

## 2. Shared message builder

- [x] 2.1 Rewrite `src/hostwatch/messages.py` around `machine_label()` and `build()` (design D3): header `:desktop_computer: <label> · <event>`, fallback `<label> · <summary>`, event fields then Local IP then Users, the users rendering with `_No users logged in_`, the optional notice and the footer. Turn `boot_message`, `shutdown_message`, `login_message` and `test_message` into wrappers that take `machine`, `local_ips` and `users`. Remove the Host and Event fields. Verify by rewriting `tests/test_messages.py`: label with and without a name (and a name equal to the hostname), header and fallback for every type including the boot warning, field order ending in Local IP and Users, users rendering with a count, the empty users text, and escaping.
- [x] 2.2 Add `machine_name` (`[display]`, optional, stripped, empty means unset) to `config.py`. Add a commented-out example to `config.example.ini`. Verify with config tests (unset by default, value read and stripped) and that the example still loads.

## 3. Commands

- [x] 3.1 In `cli.py`, add `_identity(cfg)` returning the label, local IPs and users, and use it in boot (per attempt), shutdown and test. Verify that the CLI tests pass with `sessions.logged_in_users` mocked, that the boot dry run shows the new header and the Users field, and that `hostwatch test --dry-run --config config.example.ini` prints the label, local IP and users fields.
- [x] 3.2 Make the login payload a per-attempt closure. In the detached child, wait up to 3 s (0.5 s polls) for logind to report a session for `PAM_USER` (and `PAM_RHOST` for SSH) before the first build (design D4). Verify with tests: the closure is passed to `post`, the wait stops early when the session appears, it gives up after the limit and still sends, and dry runs don't wait.

## 4. Documentation

- [x] 4.1 Update `README.md`:
  - the message descriptions with the new header and fallback format
  - a new "Using HostWatch on several machines" section: one webhook and channel shared by many PCs, `machine_name`, how push previews start with the machine, what the Users field shows and where it comes from
  - the `machine_name` row in the config table

  Verify that the table matches `config.example.ini` and that the documented commands run.

## 5. Acceptance on Ubuntu 24.04 (with the final install)

- [ ] 5.1 Install on two machines with different hostnames (one with `machine_name` set) posting to the same channel, then reboot both. Verify that the two boot push notifications are distinguishable from the preview text alone (`office-pc · Booted at …` vs `Office PC (home-pc) · Booted at …`).
- [ ] 5.2 With one desktop session and one SSH session open (SSH from another host), run `sudo hostwatch test`. Verify that the Users field lists both, `<user> · desktop` and `<user> · ssh from <remote IP>`, and that extra terminal windows in the desktop add nothing.
- [ ] 5.3 With auto-login disabled, reboot and don't log in. Verify that the boot message's Users field reads "No users logged in", with no `gdm` entry.

## Workflow follow-up

- Archive with `/opsx:archive` after acceptance. This syncs the new `message-identity` and `logged-in-users`, plus `boot-notification`, `shutdown-notification`, `login-notification`, `slack-delivery` and `hostwatch-config`.
