#!/usr/bin/env bash
# Install HostWatch: boot, shutdown, heartbeat and login notifications to Slack.
#
#   sudo ./install.sh                # first install: asks for the webhook URL
#                                    # (hidden) and an optional machine name
#   sudo ./install.sh                # re-run: shows the existing config, with the
#                                    # webhook masked, and asks "Use this
#                                    # configuration? [Y/n]"
#   sudo ./install.sh --yes          # re-run without questions; keeps the config
#   sudo ./install.sh --reconfigure  # always asks for a new webhook
#
# Without a terminal (from a script) an existing config is kept. To pass the
# webhook without a prompt, for a first install or with --reconfigure:
#
#   read -rs SLACK_WEBHOOK_URL && export SLACK_WEBHOOK_URL
#   sudo --preserve-env=SLACK_WEBHOOK_URL ./install.sh
#
# Never put the webhook on a command line: shell history, process listings
# and sudo logs record it. This script never prints it in full.
#
# Safe to run again: program files are updated, and an existing config is
# only changed when you ask for a new webhook, after saving it to
# config.ini.bak.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [--yes | --reconfigure]

  --yes          keep an existing /etc/hostwatch/config.ini without asking
  --reconfigure  ask for a new webhook URL (or take it from SLACK_WEBHOOK_URL);
                 the previous config is saved to /etc/hostwatch/config.ini.bak
  -h, --help     show this help
EOF
}

assume_yes=0
reconfigure=0
for arg in "$@"; do
    case "$arg" in
        --yes) assume_yes=1 ;;
        --reconfigure) reconfigure=1 ;;
        -h|--help) usage; exit 0 ;;
        *)
            # Not printed: a webhook pasted as an argument by mistake is a secret.
            echo "install.sh: unknown option" >&2
            usage >&2
            exit 2
            ;;
    esac
done
if [[ $assume_yes -eq 1 && $reconfigure -eq 1 ]]; then
    echo "install.sh: --yes and --reconfigure cannot be used together" >&2
    usage >&2
    exit 2
fi

LIB_DIR=/usr/local/lib/hostwatch
BIN=/usr/local/bin/hostwatch
UNIT=/etc/systemd/system/hostwatch-boot.service
SHUTDOWN_UNIT=/etc/systemd/system/hostwatch-shutdown.service
HEARTBEAT_SERVICE=/etc/systemd/system/hostwatch-heartbeat.service
HEARTBEAT_TIMER=/etc/systemd/system/hostwatch-heartbeat.timer
HEARTBEAT_DROPIN=/etc/systemd/system/hostwatch-heartbeat.timer.d/interval.conf
PAM_PROFILE=/usr/share/pam-configs/hostwatch
CONF_DIR=/etc/hostwatch
CONF="$CONF_DIR/config.ini"
STATE_DIR=/var/lib/hostwatch
PAM_SESSION=/etc/pam.d/common-session
PAM_HOOK_RE='pam_exec\.so.*/usr/local/bin/hostwatch login'

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check a webhook entered at install. $1 is the webhook, $2 says what is kept
# when it is refused. The value is never printed: it is the secret.
check_webhook() {
    if [[ "$1" != https://hooks.slack.com/* ]]; then
        echo "install.sh: the webhook must start with https://hooks.slack.com/ - $2" >&2
        return 1
    fi
    if [[ "$1" =~ [[:space:][:cntrl:]] ]]; then
        echo "install.sh: the webhook is invalid (it contains spaces or control characters," \
            "for example an inline comment) - $2" >&2
        return 1
    fi
}

# Config edits go through a root-only temporary file next to the config, and
# values reach awk through the environment, never on a command line.
conf_tmp() {
    (umask 077 && mktemp "$CONF_DIR/.config.XXXXXX")
}

commit_conf() {
    install -m 600 -o root -g root "$1" "$CONF"
    rm -f "$1"
}

set_webhook() {
    local tmp
    tmp="$(conf_tmp)"
    WEBHOOK="$1" awk '
        /^[[:space:]]*webhook_url[[:space:]]*=/ { print "webhook_url = " ENVIRON["WEBHOOK"]; next }
        { print }
    ' "$CONF" > "$tmp"
    commit_conf "$tmp"
}

# Set [display] machine_name: replace the (possibly commented) machine_name
# line in [display], or add one to that section, or add the section.
set_machine_name() {
    local tmp
    tmp="$(conf_tmp)"
    NAME="$1" awk '
        /^[[:space:]]*\[/ {
            if (in_display && !done) { print "machine_name = " ENVIRON["NAME"]; done = 1 }
            in_display = ($0 ~ /^[[:space:]]*\[display\]/)
        }
        in_display && !done && /^[[:space:]]*#?[[:space:]]*machine_name[[:space:]]*=/ {
            print "machine_name = " ENVIRON["NAME"]; done = 1; next
        }
        { print }
        END {
            if (!done) {
                if (!in_display) print "\n[display]"
                print "machine_name = " ENVIRON["NAME"]
            }
        }
    ' "$CONF" > "$tmp"
    commit_conf "$tmp"
}

if [[ $EUID -ne 0 ]]; then
    echo "install.sh: must be run as root (try: sudo $0)" >&2
    exit 1
fi

if [[ $reconfigure -eq 1 && ! -t 0 && -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "install.sh: --reconfigure needs a terminal to ask for the webhook, or" \
        "SLACK_WEBHOOK_URL in the environment; nothing was changed" >&2
    exit 1
fi

for cmd in python3 systemctl pam-auth-update ip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "install.sh: required command not found: $cmd" >&2
        exit 1
    fi
done

echo "Installing program files"
install -d -m 755 "$LIB_DIR/hostwatch"
rm -f "$LIB_DIR"/hostwatch/*.py
install -m 644 "$SRC_DIR"/src/hostwatch/*.py "$LIB_DIR/hostwatch/"
rm -rf "$LIB_DIR/hostwatch/__pycache__"
install -m 755 "$SRC_DIR/bin/hostwatch" "$BIN"
install -m 644 "$SRC_DIR/systemd/hostwatch-boot.service" "$UNIT"
install -m 644 "$SRC_DIR/systemd/hostwatch-shutdown.service" "$SHUTDOWN_UNIT"
install -m 644 "$SRC_DIR/systemd/hostwatch-heartbeat.service" "$HEARTBEAT_SERVICE"
install -m 644 "$SRC_DIR/systemd/hostwatch-heartbeat.timer" "$HEARTBEAT_TIMER"
install -m 644 "$SRC_DIR/pam/hostwatch" "$PAM_PROFILE"

# First install only: record a clean state so the first boot after install
# shows no unclean-shutdown warning. A re-run leaves the record alone, so a
# crash after it is still reported.
if [[ ! -d $STATE_DIR ]]; then
    install -d -m 755 -o root -g root "$STATE_DIR"
    : > "$STATE_DIR/clean_shutdown"
fi

install -d -m 755 -o root -g root "$CONF_DIR"
if [[ -e "$CONF" ]]; then
    # The summary comes from the installed program: it parses the file the same
    # way the notifications do and masks the webhook before printing it.
    if ! summary="$("$BIN" config-summary --config "$CONF" --example "$SRC_DIR/config.example.ini")"; then
        echo "install.sh: cannot read $CONF (see the error above); fix it and run install.sh again" >&2
        exit 1
    fi
    echo "Existing HostWatch configuration found:"
    missing=()
    while IFS='=' read -r key value; do
        case "$key" in
            webhook) printf '  %-13s: %s\n' "webhook URL" "$value" ;;
            machine_name) printf '  %-13s: %s\n' "machine_name" "$value" ;;
            heartbeat) printf '  %-13s: %s\n' "heartbeat" "$value" ;;
            missing) missing+=("$value") ;;
        esac
    done <<< "$summary"
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "  Settings this version supports that your config does not set (defaults are used):"
        printf '    %s\n' "${missing[@]}"
    fi

    want_new=0
    if [[ $reconfigure -eq 1 ]]; then
        want_new=1
    elif [[ $assume_yes -eq 0 && -t 0 ]]; then
        read -r -p "Use this configuration? [Y/n] " answer || answer=""
        case "$answer" in
            n|N|no|No|NO) want_new=1 ;;
        esac
    fi
    if [[ -n "${SLACK_WEBHOOK_URL:-}" && $reconfigure -eq 0 ]]; then
        echo "NOTE: SLACK_WEBHOOK_URL was ignored and the existing webhook kept;" \
            "use --reconfigure to replace it." >&2
    fi

    webhook=""
    if [[ $want_new -eq 1 ]]; then
        if [[ $reconfigure -eq 1 && -n "${SLACK_WEBHOOK_URL:-}" ]]; then
            webhook="$SLACK_WEBHOOK_URL"
        else
            read -r -s -p "New Slack webhook URL (leave empty to keep the current one): " webhook \
                || webhook=""
            echo
        fi
    fi
    if [[ -z "$webhook" ]]; then
        echo "Keeping existing $CONF"
    elif check_webhook "$webhook" "keeping the existing configuration"; then
        # Never change the config without a copy of the previous one.
        install -m 600 -o root -g root "$CONF" "$CONF.bak"
        set_webhook "$webhook"
        echo "Webhook replaced in $CONF (previous file saved as $CONF.bak)"
    fi
    unset webhook
else
    echo "Creating $CONF"
    install -m 600 -o root -g root "$SRC_DIR/config.example.ini" "$CONF"

    webhook="${SLACK_WEBHOOK_URL:-}"
    if [[ -z "$webhook" && -t 0 ]]; then
        read -r -s -p "Slack webhook URL (leave empty to edit later): " webhook || webhook=""
        echo
    fi
    if [[ -n "$webhook" ]] && check_webhook "$webhook" "keeping the placeholder"; then
        set_webhook "$webhook"
        echo "Webhook saved to $CONF"
    fi
    unset webhook

    if [[ -t 0 ]]; then
        read -r -p "Machine name shown in messages (optional, Enter for the hostname only): " name \
            || name=""
        if [[ "$name" =~ [[:cntrl:]] ]]; then
            echo "install.sh: the machine name contains control characters - not set" >&2
        elif [[ -n "${name// /}" ]]; then
            set_machine_name "$name"
            echo "Machine name saved to $CONF"
        fi
    fi
fi

# The file holds the webhook secret: keep it root-only, also when it was
# created or changed by hand.
if [[ "$(stat -c '%U:%G %a' "$CONF")" != "root:root 600" ]]; then
    chown root:root "$CONF"
    chmod 600 "$CONF"
    echo "Corrected the permissions of $CONF to root:root 600"
fi

if grep -q "REPLACE/WITH/YOUR-WEBHOOK" "$CONF"; then
    echo "NOTE: set webhook_url in $CONF before notifications can be sent." >&2
fi

# Apply [heartbeat] interval_minutes to the timer through a drop-in, so the
# unit file itself stays an unmodified copy from the repository.
if ! interval="$("$BIN" heartbeat-interval --config "$CONF")"; then
    echo "install.sh: fix [heartbeat] interval_minutes in $CONF and run install.sh again" >&2
    exit 1
fi
# An empty assignment to any timer option resets ALL timers (systemd.timer(5)),
# so there is exactly one reset, first: a second one would also clear the
# values set before it. OnActiveSec counts from when the timer starts (early
# in boot, or the restart below), so a schedule exists at every boot and a
# long-running host does not fire at once after install.
dropin_content="[Timer]
OnBootSec=
OnActiveSec=${interval}min
OnUnitActiveSec=${interval}min"
interval_changed=0
if [[ ! -e "$HEARTBEAT_DROPIN" || "$(cat "$HEARTBEAT_DROPIN")" != "$dropin_content" ]]; then
    install -d -m 755 "$(dirname "$HEARTBEAT_DROPIN")"
    printf '%s\n' "$dropin_content" > "$HEARTBEAT_DROPIN"
    chmod 644 "$HEARTBEAT_DROPIN"
    interval_changed=1
fi

echo "Enabling boot notification"
systemctl daemon-reload
# No --now: starting it here would send a boot message during install.
systemctl enable hostwatch-boot.service

echo "Enabling shutdown notification"
# --now arms it for the first shutdown after install; it never restarts an
# active unit, so re-running install.sh sends nothing.
systemctl enable --now hostwatch-shutdown.service

echo "Enabling heartbeat every ${interval} min"
systemctl enable hostwatch-heartbeat.timer
if [[ $interval_changed -eq 1 ]]; then
    # Apply the new interval: the next heartbeat comes one interval from now.
    systemctl restart hostwatch-heartbeat.timer
else
    # No-op when already active, so an unchanged re-run sends nothing.
    systemctl start hostwatch-heartbeat.timer
fi
# A timer can be active yet never fire (see the drop-in note above): check
# that systemd has a monotonic trigger and a next run for it.
timers="$(systemctl show hostwatch-heartbeat.timer -p TimersMonotonic --value)"
next="$(systemctl show hostwatch-heartbeat.timer -p NextElapseUSecMonotonic --value)"
systemctl list-timers hostwatch-heartbeat.timer --no-pager || true
if [[ ! "$timers" =~ On(Unit)?ActiveUSec ]] || [[ -z "$next" || "$next" == 0 || "$next" == infinity ]]; then
    cat >&2 <<'EOF'
install.sh: WARNING: hostwatch-heartbeat.timer has no next run, so no heartbeats
will be sent. Inspect it with:

    systemctl list-timers hostwatch-heartbeat.timer
    systemctl show hostwatch-heartbeat.timer -p TimersMonotonic -p NextElapseUSecMonotonic

EOF
fi

echo "Enabling login hook"
pam-auth-update --package --enable hostwatch
# pam-auth-update silently leaves a hand-edited common-session unchanged.
if ! grep -Eq "$PAM_HOOK_RE" "$PAM_SESSION"; then
    cat >&2 <<EOF
install.sh: the login hook is NOT active: $PAM_SESSION has no HostWatch line.
pam-auth-update does not change a hand-edited $PAM_SESSION. Add this line to it:

    session optional pam_exec.so quiet /usr/local/bin/hostwatch login

Everything else is installed: boot, shutdown and heartbeat messages work.
EOF
    exit 1
fi

echo
echo "Done. Send a test message with:  sudo hostwatch test"
