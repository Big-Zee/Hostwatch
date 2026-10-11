# HostWatch security review (second pass): 2026-10-11

Scope: the changes on branch `security-fixes` (commits `5b7a7d1..be6644c`) compared with `main` (`5b7a7d1`). These changes resolve the findings in [security-review-2026-10-11.md](security-review-2026-10-11.md). The review covers only new security problems these changes might introduce. Problems already present on `main` are out of scope.

Method: static review of the diff to `bin/hostwatch`, `install.sh`, `uninstall.sh`, `systemd/hostwatch-boot.service`, `systemd/hostwatch-shutdown.service` and every changed file in `src/hostwatch/`, plus the PAM profile for context. Only HIGH and MEDIUM issues with at least 80% confidence that they can be exploited count as findings. Test files, documentation and the OpenSpec change were not reviewed for vulnerabilities. No code was run and nothing was tested on an Ubuntu host.

## Summary

**The changes add no vulnerabilities.** Every change keeps or narrows what an attacker can do, and none of them creates a new way in.

| # | Severity | Area | Finding |
|---|---|---|---|
| — | — | — | No findings |

## What was checked

### Installed command (`bin/hostwatch`)

- The PAM hook and the systemd units run `/usr/local/bin/hostwatch`. `install.sh` installs it as a regular root-owned file with mode `755`, so `realpath(__file__)` equals the installed path. Root therefore always imports from `/usr/local/lib/hostwatch`.
- The checkout's `src/` is used only when the script is run from somewhere else and `src/hostwatch/cli.py` exists next to it. Only someone who can already run that script as root can trigger that.
- The shebang is still `#!/usr/bin/python3 -I`, so `PYTHON*` environment variables, the user site directory and the current directory are ignored.
- On `main`, any `src/hostwatch` directory next to the script's parent was used. The new rule is stricter.

### Login hook (runs as root on every PAM session)

- `HOSTWATCH_CONFIG` is ignored outside dry runs, because `_load_config` is given `config.DEFAULT_PATH`. This removes a lever and adds none.
- `PAM_USER`, `PAM_RHOST` and `PAM_SERVICE` only reach Slack text that is already escaped. They never reach a shell or a file path.
- The `SIGALRM` deadline is armed only in the real detached child (`detach is None` and `fork` exists). It has no handler, so it cannot run anything an attacker controls.
- No new files are written under `/tmp` or `/var/lib/hostwatch`, so there is no new symlink exposure.

### Slack delivery (`slack.py`)

- The new `https://` check runs before `urlopen`, which blocks `file:` and other schemes.
- `_describe` drops the exception text for `InvalidURL` and `ValueError`, so the webhook no longer appears in the journal.
- Catching `ValueError` adds no new attack surface.

### Escaping (`messages.py`, `processes.py`)

- `messages.py` now escapes `&`, `<` and `>` in the fallback `text`.
- In `processes.py`, `_literal` escapes the same three characters. It also replaces the backtick with U+02CB, so a cell cannot close the code block, and replaces control characters (Unicode category `Cc`) with `?`.
- Both escape text that was not escaped before. No way around them was found.

### Configuration (`config.py`)

- The file is decoded as `utf-8-sig`, and invalid UTF-8 counts as a config error.
- The new `_well_formed` check rejects whitespace and control characters and requires a host.
- Error messages never quote the URL.

### Installer and uninstaller

- An existing config is reset to `root:root 600` on every run.
- The webhook still reaches `awk` through the environment, not the command line. Values with whitespace or control characters are refused and never printed.
- `mktemp` creates its temporary files inside the root-owned `/etc/hostwatch`.
- Both scripts check for the PAM hook line in `/etc/pam.d/common-session` with a fixed pattern.
- `uninstall.sh` refuses to remove anything while the hook line is still there. It only removes fixed, root-owned paths.
- No command injection or file-permission problem was found.

### systemd units

Only the ordering and dependency directives changed (`DefaultDependencies=no` with explicit dependencies, `RemainAfterExit=yes`, `IgnoreOnIsolate=yes`, and shutdown ordered after `network.target` and `nss-lookup.target`). The user, the privileges and the command each unit runs are unchanged.

## Considered and rejected

### State directory no longer reset on re-install

`install.sh` now creates `/var/lib/hostwatch` and the clean-shutdown record only on first install (Finding #13 of the first review). On `main`, `install -d` ran on every install and reset the directory to `root:root 755`; that no longer happens on a re-run.

Rejected because exploiting it needs someone who already had root to have loosened the directory's permissions. It is hardening at most, not a vulnerability. If you want the old behaviour back, keep the clean-state record first-install-only but reset the directory's owner and mode on every run.

## Open items carried over

These items come from the first review and are not new. They are listed here for completeness:

- Deferred findings: #3, #5, #11 (command paths), #14, #19, #20 and #21. The reasons are in the first review's Resolution section.
- Still to do on an Ubuntu 24.04 VM: `shellcheck`, `systemd-analyze verify` (tasks 8.2 and 8.3), and the VM checks in section 9 of `openspec/changes/fix-security-review-findings/tasks.md`.
