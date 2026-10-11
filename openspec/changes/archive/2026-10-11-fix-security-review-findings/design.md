# Design

## Context

See proposal.md for the findings being fixed, deferred and rejected, and the delta specs for the required behaviour. Finding numbers refer to `docs/security-review-2026-10-11.md`.

Constraints that shape every decision:
- Boot, shutdown and login must never depend on HostWatch succeeding.
- The program uses the Python 3 standard library only.
- Re-running `install.sh` must bring an existing install up to date. It already overwrites the program files, units and PAM profile and runs `daemon-reload`, so code and unit fixes reach existing hosts without migration steps.
- Fixes stay local to the defect: no message-content or schedule changes, and no refactoring beyond what a fix needs.

## Goals / Non-Goals

**Goals:**
- Each fix is the smallest change that removes its defect, and is covered by a unit test or a VM check.

**Non-Goals:**
- Fixing the deferred findings (#3, #5, #11 command paths, #14, #19, #20, #21). Their reasons are in proposal.md.
- Detecting or migrating slack-heartbeat installs (#17, rejected).

## Decisions

### D1. Boot unit without default dependencies (Finding #1)

A target adds an implicit `After=` on every unit it wants, unless that unit sets `DefaultDependencies=no`. `hostwatch-boot.service` sets it and declares what it still needs:

```
DefaultDependencies=no
Requires=sysinit.target
After=sysinit.target basic.target network-online.target
Wants=network-online.target
Conflicts=shutdown.target
Before=shutdown.target
```

`multi-user.target` still pulls the unit in through `WantedBy=` but no longer waits for it. The unit itself still starts only after the network is online, as boot-notification requires. `/var/lib` is available through `sysinit.target`, which includes the local file systems.

Alternative considered: start the boot notification from a timer (`OnBootSec=1s`). Rejected because it needs a new unit file, more install and uninstall steps, and has the same effect.

### D2. Shutdown unit ordered after `network.target` (Finding #1)

`hostwatch-shutdown.service` replaces `Wants=` and `After=network-online.target` with `After=network.target nss-lookup.target` and keeps its default dependencies.
- **At boot:** `network.target` is reached early, so the target no longer waits for the network to come online.
- **At shutdown:** units are stopped in reverse order. The network managers (NetworkManager, systemd-networkd, ifupdown's `networking.service`) and systemd-resolved are ordered `Before=network.target` and `Before=nss-lookup.target`, so they are still running when `ExecStop` sends the message. The ordering that matters at stop time is unchanged.

`hostwatch-heartbeat.service` keeps `network-online.target`: a timer starts it, so no target waits for it.

### D3. One boot message per boot through unit state (Finding #2)

The boot unit gets `RemainAfterExit=yes` and `IgnoreOnIsolate=yes`. Once it has run, it stays "active" for the rest of the boot. `systemctl start` or `isolate` of a target then has nothing to start, and isolating to rescue does not stop it. Shutdown and soft-reboot still stop it through `Conflicts=shutdown.target`, so the next boot runs it again.

Alternative considered: a stored kernel boot ID. Rejected because `systemctl soft-reboot` keeps the kernel boot ID. The boot message after a soft reboot would be suppressed and the clean-shutdown marker left unconsumed.

This relies on D9: the boot command always exits 0. Otherwise a failed unit would be started again by the next `start` of the target.

### D4. Login sender bounded by `SIGALRM` (Finding #4)

In the detached grandchild only (the real `_detach` path), `run_login` calls `signal.alarm(60)` before doing any work. It installs no handler, so the default action ends the process.
- A Python handler would not help: handlers run only between bytecodes, and a hung `getaddrinfo` blocks inside C.
- The normal worst case is about 40 s: a 3 s session wait, 3 attempts with a 10 s timeout, and 7 s of delays. That ends well inside the limit and logs as before.

The cost: only a lookup hung past 60 s ends without a journal entry.

### D5. Wrapper chooses the checkout only when it is not the installed copy (Finding #6)

`bin/hostwatch` resolves its own real path. It uses `<checkout>/src` only when that path is not `/usr/local/bin/hostwatch` and `<checkout>/src/hostwatch/cli.py` exists. In every other case it uses `/usr/local/lib/hostwatch`.
- The repository file and the installed file stay identical, and `install.sh` keeps copying it unchanged.
- A symlink from `/usr/local/bin/hostwatch` into a checkout resolves to the checkout and uses it. That is an explicit administrator choice.

Alternative considered: `install.sh` rewrites the wrapper while copying it. Rejected because the installed and repository copies would then differ.

### D6. No exception text in logs where it could carry the URL (Finding #7)

- **`config.validate`:** after the `https://` prefix check, it rejects a webhook that contains any whitespace or control character, or whose `urlsplit` has no host. The message says the URL is invalid and that inline comments are not supported, and it never quotes the value.
- **`slack._describe`:** for `http.client.InvalidURL` and any `ValueError` it returns only the class name. Other exceptions keep their reason, because socket and SSL errors carry no URL path.
- **`slack.post`:** it checks `https://` itself before `urlopen`. That is defence in depth when it is called without validated config, and it justifies `# nosec B310` for bandit.
- **Catch-alls:** a small `cli._log_unexpected(event, exc)` replaces the message text in the existing catch-alls (heartbeat, shutdown, login) and the new boot one (D9). It logs `<event>: unexpected error: <Class> at <file>:<line>`, taken from the innermost traceback frame, with the file reduced to its base name.
- **`install.sh`:** it refuses a supplied webhook that matches `[[:space:][:cntrl:]]`.

### D7. Literal host values in Slack (Finding #8)

- **Process table:** `processes.format_table` fits and pads each cell first, then makes it literal:
  - `&`, `<` and `>` become entities
  - a backtick becomes `ˋ` (U+02CB)
  - control characters become `?`

  Slack renders an entity as one character, so escaping after padding keeps the columns aligned. The helper lives in `processes` so `processes` does not import `messages`.
- **Fallback text:** `messages.build` escapes the whole plain-text fallback once (`_escape(f"{machine} · {summary}")`).
  - The summaries are unescaped today, so nothing is escaped twice.
  - The header is `plain_text` and Slack does not parse it, so it stays unescaped.
  - Field values are already escaped.

### D8. Login hook ignores `HOSTWATCH_CONFIG` (Finding #11)

When not in dry-run mode and no `--config` was given, `run_login` passes `config.DEFAULT_PATH` explicitly. `resolve_path` returns an explicit path before it looks at the environment, so `config.py` does not change. Dry runs and `--config` behave as before.

### D9. Boot command cannot fail its unit (Finding #18)

- **`run_boot`:** its body after the marker check moves into `try/except Exception`, which logs through `_log_unexpected` and returns 0, the same pattern the shutdown, heartbeat and login commands already use.
- **`config.load`:** it opens the file with `encoding="utf-8-sig"`, which strips a byte-order mark if there is one, and turns `UnicodeDecodeError` into `ConfigError("config <path> is not valid UTF-8")`.
- **Command calls:** `sessions._run`, `netinfo._systemctl` and `netinfo.local_addresses` pass `errors="replace"` to `subprocess.run`, so odd bytes in `who`, `loginctl` or `ip` output cannot raise.

### D10. Installer and uninstaller (Findings #9, #10, #12, #13, #15, #16)

**`install.sh`:**
- **Finding #10:** after the config block, compare `stat -c '%U:%G %a'` with `root:root 600`. If they differ, run `chown root:root` and `chmod 600` and print that the permissions were corrected.
- **Finding #12:** after `pam-auth-update --enable`, run `grep -Eq 'pam_exec\.so.*/usr/local/bin/hostwatch login' /etc/pam.d/common-session`. If the line is missing, print the manual fix and exit 1. Every other step has already completed, so only the login hook is missing.
- **Finding #13:** create `/var/lib/hostwatch` and the clean marker only `if [[ ! -d $STATE_DIR ]]`.
- **Finding #9:** the header comment shows the prompt and `--preserve-env` forms only.

**`uninstall.sh`:**
- **Finding #12:** after the PAM step, run the same `grep` regardless of whether the profile existed. If the line is still there, print the manual fix and exit 1 before anything else is removed.
- **Finding #16:**
  - Every `systemctl disable` runs regardless of whether its unit file exists, with `|| true`.
  - The boot unit is disabled with `--now`.
  - The known enablement links are removed explicitly, because `disable` cannot find a unit whose file was deleted: `multi-user.target.wants/hostwatch-{boot,shutdown}.service` and `timers.target.wants/hostwatch-heartbeat.timer`.
  - `systemctl reset-failed` runs for each HostWatch unit after `daemon-reload`, with `|| true`.

**README:**
- **Finding #9:** the hidden prompt and `read -rs SLACK_WEBHOOK_URL; export SLACK_WEBHOOK_URL; sudo --preserve-env=SLACK_WEBHOOK_URL ./install.sh` replace `sudo SLACK_WEBHOOK_URL=… ./install.sh`. The README warns about history, `ps` and sudo logs.
- **Finding #15:** the Heartbeat section adds that the first install on a host that has been up longer than one interval sends one heartbeat right away.

### D11. Verification tooling

- **bandit:**
  - The only medium findings expected are B310 (urlopen) and B108 (`/tmp/env.ini` in `tests/test_config.py`). B310 is handled by D6. For B108 the test path becomes `/etc/hostwatch-test/env.ini`.
  - Low findings (B404, B603, B607 subprocess use; B101 asserts in tests; B110 in `log.py`) are expected and accepted.
- **shellcheck and `systemd-analyze verify`:** run on Ubuntu 24.04. Neither is available on the development machine.

## Risks / Trade-offs

- [A unit with `DefaultDependencies=no` loses implicit ordering that later systemd versions might add] → The dependencies systemd documents as defaults are declared explicitly, and the boot chain is checked with `systemd-analyze critical-chain` in the VM.
- [Hosts upgraded mid-boot] → After `install.sh` runs, the boot unit that ran earlier in the current boot is already inactive, so one `isolate` before the next reboot could still send one extra boot message. From the next boot on, D3 applies. Not worth special handling.
- [The `SIGALRM` kill leaves no journal entry for a lookup hung past 60 s] → Accepted. The normal failure paths finish earlier and log as before.
- [`install.sh` now exits 1 when PAM is hand-edited] → Intended. The message says exactly what is missing and how to add it, and everything else is installed.
- [`uninstall.sh` stops early when the PAM line persists] → Intended. Logins then keep a working program instead of an `exec` failure, and a re-run after the manual fix completes the uninstall.
- [Escaping changes how names containing `& < >` or a backtick look] → Only such names are affected, and Slack shows `& < >` the same after decoding. Only a backtick is visibly replaced.

## Migration Plan

1. On each host, from the updated checkout, run `sudo ./install.sh`. The wrapper, package, units and PAM profile are replaced, `daemon-reload` runs, and the config permissions are checked. The unit ordering changes take effect at the next boot.
2. Rollback: check out the previous commit and run `sudo ./install.sh` again. Nothing in this change alters stored state, the config format or the paths.
