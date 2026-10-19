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
LAST_ALIVE_SERVICE=/etc/systemd/system/hostwatch-last-alive.service
LAST_ALIVE_TIMER=/etc/systemd/system/hostwatch-last-alive.timer
LAST_ALIVE_DROPIN=/etc/systemd/system/hostwatch-last-alive.timer.d/interval.conf
PAM_PROFILE=/usr/share/pam-configs/hostwatch
CONF_DIR=/etc/hostwatch
CONF="$CONF_DIR/config.ini"
STATE_DIR=/var/lib/hostwatch
PAM_SESSION=/etc/pam.d/common-session
PAM_HOOK_RE='pam_exec\.so.*/usr/local/bin/hostwatch login'
# The services hostwatch login announces (see LOGIN_SERVICES in cli.py).
LOGIN_PAM_SERVICES=(sshd login gdm-password gdm-autologin gdm-fingerprint gdm-smartcard
                     lightdm lightdm-autologin sddm sddm-autologin)

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

# Warn if any login service runs pam_env with user_readenv=1 before including
# common-session: on such a host the login hook runs with an environment the
# logging-in user partly controls through ~/.pam_environment (PATH,
# LD_PRELOAD, OPENSSL_CONF/SSL_CERT_FILE/https_proxy). The hook defends
# itself (bin/hostwatch sanitizes PAM_TYPE-bearing environments down to
# PAM_* plus a fixed PATH/LANG before anything else runs), but LD_PRELOAD on
# python3 itself cannot be fixed from inside Python, so this is still worth
# the admin's attention. Informational only: never blocks the install.
check_pam_env_order() {
    local svc file line_env line_common
    for svc in "${LOGIN_PAM_SERVICES[@]}"; do
        file="/etc/pam.d/$svc"
        [[ -f "$file" ]] || continue
        line_env="$(grep -n 'pam_env\.so.*user_readenv=1' "$file" | head -1 | cut -d: -f1)" || true
        line_common="$(grep -n '@include[[:space:]]\+common-session\b' "$file" \
            | head -1 | cut -d: -f1)" || true
        if [[ -n "$line_env" && -n "$line_common" && "$line_env" -lt "$line_common" ]]; then
            echo "install.sh: WARNING: $file runs pam_env with user_readenv=1 before" \
                "common-session is included. A user logging in through this service can" \
                "set PATH, LD_PRELOAD or TLS-related variables (OPENSSL_CONF, SSL_CERT_FILE," \
                "https_proxy) for everything that session's login hooks run, as root." \
                "See docs/security-review-third.md, finding #1." >&2
        fi
    done
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

# Apply an interval in minutes to a timer through a drop-in, so the unit
# file itself stays an unmodified copy from the repository, then enable it
# and verify it has a next run. An empty assignment to any timer option
# resets ALL timers (systemd.timer(5)), so there is exactly one reset,
# first: a second one would also clear the values set before it.
# OnActiveSec counts from when the timer starts (early in boot, or the
# restart below), so a schedule exists at every boot and a long-running
# host does not fire at once after install.
apply_timer_interval() {
    local timer="$1" dropin="$2" interval="$3" label="$4"
    local dropin_content changed=0
    dropin_content="[Timer]
OnBootSec=
OnActiveSec=${interval}min
OnUnitActiveSec=${interval}min"
    if [[ ! -e "$dropin" || "$(cat "$dropin")" != "$dropin_content" ]]; then
        install -d -m 755 "$(dirname "$dropin")"
        printf '%s\n' "$dropin_content" > "$dropin"
        chmod 644 "$dropin"
        changed=1
        # The drop-in just changed on disk: systemd must re-read it before
        # the restart below, or the timer restarts with the stale interval
        # it already had cached in memory.
        systemctl daemon-reload
    fi
    echo "Enabling $label every ${interval} min"
    systemctl enable "$timer"
    if [[ $changed -eq 1 ]]; then
        # Apply the new interval: the next run comes one interval from now.
        systemctl restart "$timer"
    else
        # No-op when already active, so an unchanged re-run sends nothing.
        systemctl start "$timer"
    fi
    # A timer can be active yet never fire (see the drop-in note above):
    # check that systemd has a monotonic trigger and a next run for it.
    local timers next
    timers="$(systemctl show "$timer" -p TimersMonotonic --value)"
    next="$(systemctl show "$timer" -p NextElapseUSecMonotonic --value)"
    systemctl list-timers "$timer" --no-pager || true
    if [[ ! "$timers" =~ On(Unit)?ActiveUSec ]] || [[ -z "$next" || "$next" == 0 || "$next" == infinity ]]; then
        cat >&2 <<EOF
install.sh: WARNING: $timer has no next run, so $label will not fire. Inspect
it with:

    systemctl list-timers $timer
    systemctl show $timer -p TimersMonotonic -p NextElapseUSecMonotonic

EOF
    fi
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

# Confirm $CONF actually holds the webhook just written. set_webhook's awk only
# rewrites a line matching `webhook_url *=` exactly; a file using
# `webhook_url:`, a different letter case, or with no such line at all is
# left unchanged, so the caller must not report success without this check.
verify_webhook() {
    local expected masked summary
    expected="${1: -4}"
    if ! summary="$("$BIN" config-summary --config "$CONF" --example "$SRC_DIR/config.example.ini")"; then
        echo "install.sh: cannot re-read $CONF to confirm the webhook was changed" >&2
        return 1
    fi
    masked="$(awk -F= '/^webhook=/ { print substr($0, 9) }' <<< "$summary")"
    if [[ "$masked" != *"$expected" ]]; then
        echo "install.sh: the webhook in $CONF was NOT changed (no 'webhook_url = ' line" \
            "matched); edit $CONF by hand and set webhook_url under [slack]" >&2
        return 1
    fi
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
install -m 644 "$SRC_DIR/systemd/hostwatch-last-alive.service" "$LAST_ALIVE_SERVICE"
install -m 644 "$SRC_DIR/systemd/hostwatch-last-alive.timer" "$LAST_ALIVE_TIMER"
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
        verify_webhook "$webhook" || exit 1
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
        verify_webhook "$webhook" || exit 1
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

# Validate [heartbeat] interval_minutes and [uptime] settings before
# touching any timer or unit.
if ! interval="$("$BIN" heartbeat-interval --config "$CONF")"; then
    echo "install.sh: fix [heartbeat] interval_minutes in $CONF and run install.sh again" >&2
    exit 1
fi
if ! last_alive_interval="$("$BIN" uptime-interval --config "$CONF")"; then
    echo "install.sh: fix [uptime] settings in $CONF and run install.sh again" >&2
    exit 1
fi

echo "Enabling boot notification"
systemctl daemon-reload
# No --now: starting it here would send a boot message during install.
systemctl enable hostwatch-boot.service

echo "Enabling shutdown notification"
# --now arms it for the first shutdown after install; it never restarts an
# active unit, so re-running install.sh sends nothing.
systemctl enable --now hostwatch-shutdown.service

apply_timer_interval "hostwatch-heartbeat.timer" "$HEARTBEAT_DROPIN" "$interval" "heartbeat"
apply_timer_interval "hostwatch-last-alive.timer" "$LAST_ALIVE_DROPIN" "$last_alive_interval" \
    "the last-alive timer"

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
check_pam_env_order

echo
echo "Done. Send a test message with:  sudo hostwatch test"
