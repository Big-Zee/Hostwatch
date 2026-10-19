# Design

## Context

See proposal.md (Why) for the observed failure and its cause.

The relevant parts of the current code:

- `install.sh` writes `/etc/systemd/system/hostwatch-heartbeat.timer.d/interval.conf` with a reset line before each option. It restarts the timer when the drop-in changed, and otherwise starts it.
- `install.sh` handles the config in Bash. An existing file prints `Keeping existing …`. A new file is copied from `config.example.ini`, the webhook comes from `SLACK_WEBHOOK_URL` or a hidden prompt, and `awk` writes it, with the value passed through the environment.
- `install.sh` already calls a hidden subcommand, `hostwatch heartbeat-interval --config`, to read the validated interval. INI parsing therefore already lives in Python, not Bash.
- `config.py` holds the defaults (`DEFAULT_SKIP_INTERFACES`, `DEFAULT_HEARTBEAT_INTERVAL`, `PLACEHOLDER_WEBHOOK`) and never quotes the webhook in errors.
- systemd.timer(5): "If the empty string is assigned to any of these options, the list of timers is reset (both monotonic timers and OnCalendar= timers)". A reset therefore clears every timer option, not just the one it is assigned to.

## Goals / Non-Goals

**Goals:**
- A heartbeat schedule that has a trigger at every boot and after every install, and that `install.sh` checks.
- One place that reads the config and masks the webhook. That is the Python helper, so the full URL never reaches a Bash variable that might be echoed.
- Installer behaviour that is the same on every re-run, so it can be scripted (`--yes`) and is safe without a terminal.

**Non-Goals:**
- Changing the runtime webhook check in `config.py`, which still accepts any `https://` host.
- Editing user config files to add missing keys.
- A legacy `/etc/slack-heartbeat/` import.
- Changing the allowed interval range (5–1440 minutes).

## Decisions

### D1. The drop-in uses one reset, then `OnActiveSec` and `OnUnitActiveSec`

```
[Timer]
OnBootSec=
OnActiveSec=<n>min
OnUnitActiveSec=<n>min
```

- **The single reset** clears everything the base unit set. That is needed: without it, the base unit's 60-minute values would stay alongside the configured ones. Nothing follows it that could clear the new values.
- **`OnActiveSec`** counts from when the timer unit starts. At boot that is when `timers.target` is reached, a few seconds after boot, so the first heartbeat comes about one interval after boot. After `systemctl restart` in `install.sh`, it counts from the install. A long-running host therefore no longer fires at once, which removes the Finding #15 behaviour.
- **The base `hostwatch-heartbeat.timer`** gets the same pair (`OnActiveSec=60min`, `OnUnitActiveSec=60min`). A host without the drop-in still works.

Alternatives considered:
- *Fix only the reset and keep `OnBootSec`.* This would schedule the first heartbeat after boot. But a restart on a long-running host would still find `OnBootSec` in the past and fire at once, or with an earlier trigger leave the timer "elapsed". `OnActiveSec` covers both boot and install with one rule.
- *Write the interval into the base unit instead of a drop-in.* This keeps the unit file different from the repository copy and makes `systemctl cat` less clear. The drop-in stays, without the problematic second reset.
- *`Persistent=true` / `OnCalendar`.* These are wall-clock based, but the spec requires timing relative to boot.

### D2. Check after install with `systemctl show` and `list-timers`

After `start` or `restart`, the script reads two values:
- `systemctl show hostwatch-heartbeat.timer -p TimersMonotonic --value` must be non-empty and contain `OnActiveUSec` or `OnUnitActiveUSec`.
- `systemctl show -p NextElapseUSecMonotonic --value` must not be empty, `0` or `infinity`.

`systemctl list-timers hostwatch-heartbeat.timer --no-pager` is printed for the administrator. A failed check prints a warning to stderr and continues, because boot, login and shutdown messages are unaffected. `NextElapseUSecMonotonic` is used because it is machine-readable. `list-timers` output is for display only, since its format varies between versions.

### D3. A hidden `hostwatch config-summary` subcommand masks the webhook and finds missing keys

`install.sh` runs `hostwatch config-summary --config "$CONF" --example "$SRC_DIR/config.example.ini"`. It prints plain `key=value` lines that are safe to show:

- `webhook=https://hooks.slack.com/…abcd`, or `webhook=not set` for an empty or placeholder webhook
- `machine_name=…`
- `heartbeat=enabled, every 60 min`
- one `missing=[section] key (default …)` line per missing setting

Masking (`config.mask_webhook`) keeps the scheme and host and appends `…` and the last 4 characters. If the URL has no parseable host or is shorter than 8 characters, it prints `…` and the last 4 characters only.

"Missing" means present and uncommented in `config.example.ini` but absent from the user's file. The optional, commented-out `machine_name` is therefore never reported. Defaults come from `config.py`, so code and output agree.

The subcommand reads the file with the same parser as `config.load`, with `require_webhook=False`. A config that does not parse makes the subcommand exit 1, with an error that never quotes the content. `install.sh` then stops with a message to fix the file, as it already does for a bad `interval_minutes`.

The bash side never reads `webhook_url` itself. It only echoes the summary lines.

Alternative considered: masking in Bash with `sed` on the file. This duplicates the INI parsing, misreads BOMs and inline values, and loads the secret into a shell variable.

### D4. The installer flow in `install.sh`

```
parse args: --yes | --reconfigure | -h/--help  (anything else → usage, exit 2)
[existing program-file install steps]
if config exists:
    print summary (D3)
    if --reconfigure:               want_new=1
    elif --yes or no TTY:           want_new=0
    else: ask "Use this configuration? [Y/n]"; n/N/no → want_new=1
    if SLACK_WEBHOOK_URL set and not --reconfigure: note "ignored; use --reconfigure"
    if want_new:
        get webhook: SLACK_WEBHOOK_URL (if --reconfigure) or hidden prompt (TTY)
        no source and no TTY → error, exit 1 (before writing)
        empty → keep file, no backup
        invalid → message without the value, keep file
        valid → cp -p config.ini config.ini.bak; chmod 600; awk-replace webhook_url → tmp → install
else:
    create from example, then webhook (env or prompt, validated as below), then machine_name prompt (TTY only)
permission fix-up (unchanged)
placeholder note (unchanged)
```

- **TTY detection** uses `-t 0`, as today.
- **The Y/n prompt** reads one line with `read -r`. Only `n`, `N`, `no` and `NO` mean no, and anything else is yes, so a stray key cannot trigger a change.
- **Webhook validation** shares one Bash function for the prompt and the environment variable: prefix `https://hooks.slack.com/` plus the existing whitespace and control-character check. The value never appears in a message.
- **`machine_name`** is accepted only if it has no control characters. `awk` replaces the commented `# machine_name = …` line in `[display]` or, if that line is missing, appends the key under `[display]`. The value is passed through the environment, never on the command line.
- **Backup** goes to `config.ini.bak`: `install -m 600 -o root -g root "$CONF" "$CONF.bak"`. One backup is kept, and the latest overwrites it.
- **Argument parsing** happens before the root check. `--help` works without root, and a bad flag fails before anything else.

### D5. No secrets in the journal

`install.sh` does not log to the journal. Its output goes to the terminal or the calling script. The `config-summary` subcommand writes to stdout only and never calls `log.error` with the URL. The existing journal rules for runtime errors are unchanged.

## Risks / Trade-offs

- **[Already-installed hosts keep the broken drop-in until `install.sh` is re-run]** → The README upgrade note says to re-run `install.sh` on every host. The post-install check (D2) confirms the fix on each.
- **[`OnActiveSec` counts from timer start, not from the kernel's boot]** → The difference is the few seconds until `timers.target`, which is within "about one interval".
- **[The stricter `https://hooks.slack.com/` check could reject a legitimate Slack-compatible endpoint, such as a proxy]** → It applies only at install. The runtime still accepts any `https://` URL, and an administrator can edit the file by hand.
- **[`--reconfigure` without a terminal needs the webhook in the environment]** → This is documented. The script fails before touching anything if neither source exists.
- **[The acceptance run in the request used a 3-minute interval, below the allowed minimum of 5]** → Use 5 minutes for the short-interval VM check. Changing the range is a non-goal.
- **[A `.bak` file holds the old webhook]** → It is root `600` like the config. `uninstall.sh --purge` already removes `/etc/hostwatch/`.

## Migration Plan

1. Merge, then run `sudo ./install.sh` (or `--yes`) on each host. The drop-in is rewritten, the timer restarts, and the next heartbeat comes one interval later.
2. Check with `systemctl list-timers hostwatch-heartbeat.timer`: NEXT must be set.
3. To roll back, check out the previous version and re-run `install.sh`. The config file is untouched by `--yes` runs, so nothing else needs undoing.
