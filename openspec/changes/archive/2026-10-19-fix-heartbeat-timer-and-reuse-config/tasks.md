# Tasks

Run the unit tests with `python3 -m unittest discover -s tests -t .`. Installer and timer behaviour can only be checked on an Ubuntu 24.04 host (group 5).

## 1. Heartbeat timer schedule (design D1, D2)

- [x] 1.1 In `systemd/hostwatch-heartbeat.timer`, replace `OnBootSec=60min` with `OnActiveSec=60min`, keep `OnUnitActiveSec=60min`, and update the comment. Verify that `grep -c OnBootSec systemd/hostwatch-heartbeat.timer` prints 0.
- [x] 1.2 In `install.sh`, write the drop-in as `[Timer]`, `OnBootSec=` (the single reset), `OnActiveSec=<n>min` and `OnUnitActiveSec=<n>min`, with a comment citing the systemd.timer(5) reset rule. Verify that the generated drop-in has exactly one empty assignment and that it is the first line after `[Timer]`.
- [x] 1.3 In `install.sh`, after the timer `start`/`restart`, check that `systemctl show hostwatch-heartbeat.timer -p TimersMonotonic --value` names `OnActiveUSec` or `OnUnitActiveUSec`, and that `-p NextElapseUSecMonotonic --value` is not empty, `0` or `infinity`. Print `systemctl list-timers hostwatch-heartbeat.timer --no-pager`. On failure, write a warning to stderr naming the timer and the inspect command, and continue. Verify by reading the code path with `bash -n install.sh`. The live check is task 5.2.
- [x] 1.4 Update the README Heartbeat section and the `[heartbeat] interval_minutes` comment in `config.example.ini`:
  - the first heartbeat comes one interval after boot
  - after `install.sh` (first install or interval change), the next heartbeat comes one interval after the install, and no heartbeat is sent at once
  - remove the "sends one heartbeat right away" sentences

  Verify that `grep -n "right away" README.md` finds nothing about the heartbeat.

## 2. Config summary helper (design D3, D5)

- [x] 2.1 Add `config.mask_webhook(url)`: it returns `scheme://host/…` plus the last 4 characters, `…` plus the last 4 characters when there is no parseable host or the URL is shorter than 8 characters, and `not set` for an empty or placeholder URL. Verify that new `tests/test_config.py` cases check `https://hooks.slack.com/services/T000/B000/xyzabcd` → `https://hooks.slack.com/…abcd`, the placeholder, an empty value, a host-less value, and that no result contains `T000`, `B000` or `xyzab`.
- [x] 2.2 Add `config.missing_settings(path, example_path)`. It returns `(section, key, default)` for each uncommented key in the example file that the user's file lacks, with defaults from `config.py`. Verify with `tests/test_config.py` cases:
  - a config without `[heartbeat]` reports `enabled` and `interval_minutes`
  - the commented-out `machine_name` is never reported
  - a complete config reports nothing
- [x] 2.3 Add the hidden `hostwatch config-summary --config PATH --example PATH` subcommand in `cli.py`. It prints the `webhook=`, `machine_name=`, `heartbeat=` and `missing=` lines, exits 1 with an unquoted error on an unreadable or unparsable file, and never logs the URL. Verify with `tests/test_cli.py`:
  - a config holding `https://hooks.slack.com/services/T000/B000/SECRETxyzabcd` prints the masked form
  - no captured stdout, stderr or log record contains `SECRET`
  - `heartbeat=enabled, every 60 min` is printed for the default
  - a broken file exits 1

## 3. Installer options and existing-config flow (design D4)

- [x] 3.1 Add argument parsing to `install.sh` (`--yes`, `--reconfigure`, `-h`/`--help`) before the root check. Unknown options and `--yes --reconfigure` together print usage and exit 2. Update the header comment. Verify that `./install.sh --help` works without root, and that `./install.sh --bogus` and `./install.sh --yes --reconfigure` exit 2 without changing anything.
- [x] 3.2 Add one webhook-validation function used for both the prompt and `SLACK_WEBHOOK_URL`. It requires the prefix `https://hooks.slack.com/` and no whitespace or control characters, and never prints the value. Verify by sourcing the function in a throwaway Bash session with a valid URL, `https://example.com/x`, and a URL with ` # prod`. Only the first passes, and no message contains the input.
- [x] 3.3 When the config exists:
  - print the summary from `hostwatch config-summary` and any `missing=` lines
  - decide keep or replace by the D4 rules (`--reconfigure`, `--yes`, no TTY, `[Y/n]` prompt where only `n`/`no` means no)
  - print the "SLACK_WEBHOOK_URL ignored; use --reconfigure" note when it applies
  - stop with an error before writing when a replacement is wanted but no TTY and no `SLACK_WEBHOOK_URL` exist

  Verify with `bash -n install.sh`. The behaviour is checked in task 5.3.
- [x] 3.4 When replacing the webhook:
  - an empty answer keeps the file and writes no backup
  - an invalid answer keeps the file
  - a valid answer copies the file to `config.ini.bak` with `install -m 600 -o root -g root`, then writes the new webhook with the existing `awk`/tmp/`install` pattern, passing the value through the environment

  Verify that the `awk` step changes only the `webhook_url` line by running it on `config.example.ini` in a temp dir and diffing.
- [x] 3.5 On a fresh config, validate the webhook with the 3.2 function. Then, on a TTY only, ask for an optional `machine_name` (visible input, control characters refused). Write it by replacing the `# machine_name = …` line in `[display]`, or by appending it under `[display]` if that line is absent. Verify with the `awk` step run on `config.example.ini` in a temp dir: `machine_name = Maja PC` appears under `[display]`, and nothing else changes.
- [x] 3.6 Update the README Install section:
  - the existing-config summary and `Use this configuration? [Y/n]` prompt, with an example masked line
  - `--yes`, `--reconfigure`, and the no-terminal behaviour
  - `SLACK_WEBHOOK_URL` only applying to a fresh install or `--reconfigure`
  - `config.ini.bak`
  - the `machine_name` prompt
  - the `https://hooks.slack.com/` rule
  - the list of missing settings

  Also update the "Running it again…" paragraph and the `install.sh` bullet list. Verify that every flag in `./install.sh --help` is described in the README.

## 4. Unit test run

- [x] 4.1 Run the full unit test suite and verify that it passes with no new warnings. Run `bandit -r src` (if available) and verify that it reports nothing new.

## 5. Checks on an Ubuntu 24.04 host

- [x] 5.1 Run `shellcheck install.sh` and verify that it prints no warnings. Fix any it reports.
- [x] 5.2 Set `interval_minutes = 5`, run `sudo ./install.sh --yes`, and verify all of the following:
  - no heartbeat is sent at once
  - `systemctl list-timers hostwatch-heartbeat.timer` shows NEXT about 5 min away
  - no warning is printed

  Reboot and verify that, without touching any unit, NEXT is set right after boot, the first heartbeat arrives about 5 minutes after boot, and the next ones about every 5 minutes. Repeat with `interval_minutes = 60` (first heartbeat about 60 min after boot). The request asked for a 3-minute run, but the allowed minimum is 5.
- [x] 5.3 On a host with a real config, run `sha256sum /etc/hostwatch/config.ini`, then `sudo ./install.sh` and press Enter. Verify that the summary shows the masked webhook, machine name and heartbeat, that no other configuration question is asked, and that the checksum, owner `root:root` and mode `600` are unchanged. Repeat with `sudo ./install.sh --yes` and from a script without a terminal (`sudo ./install.sh < /dev/null`), and verify that neither asks anything and the checksum is unchanged.
- [x] 5.4 Run `sudo ./install.sh`, answer `n` and enter a new webhook. Verify that `config.ini.bak` holds the previous content (compare it with the checksum from 5.3) with `root:root 600`, and that the new webhook is in `config.ini` with every other setting unchanged. Repeat with `n` and an empty answer, and verify that nothing changes and no new backup is written.
- [x] 5.5 On a fresh host (or after `sudo ./uninstall.sh --purge`), run `sudo ./install.sh`. Verify that it asks for the webhook and then the machine name, that `https://example.com/x` is refused, and that a valid webhook and `Maja PC` end up in the config.
- [x] 5.6 Use a config without a `[heartbeat]` section and run the installer. Verify that it lists the missing settings with their defaults and does not change the file.
- [x] 5.7 After tasks 5.3–5.5, check the captured installer output and `journalctl --since "<start of test>"`. Verify that `grep` for the webhook's path segments finds nothing in either.

## Workflow follow-up

- Sync the delta specs and archive the change after the Ubuntu checks pass.
