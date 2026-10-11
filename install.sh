#!/usr/bin/env bash
# Install HostWatch: boot, shutdown, heartbeat and login notifications to Slack.
#
#   sudo ./install.sh
#   sudo SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... ./install.sh
#
# Safe to run again: program files are updated, an existing config is kept.
set -euo pipefail

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

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "install.sh: must be run as root (try: sudo $0)" >&2
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

# Record a clean state so the first boot after install shows no
# unclean-shutdown warning.
install -d -m 755 -o root -g root "$STATE_DIR"
: > "$STATE_DIR/clean_shutdown"

install -d -m 755 -o root -g root "$CONF_DIR"
if [[ -e "$CONF" ]]; then
    echo "Keeping existing $CONF"
else
    echo "Creating $CONF"
    install -m 600 -o root -g root "$SRC_DIR/config.example.ini" "$CONF"

    webhook="${SLACK_WEBHOOK_URL:-}"
    if [[ -z "$webhook" && -t 0 ]]; then
        read -r -s -p "Slack webhook URL (leave empty to edit later): " webhook
        echo
    fi
    if [[ -n "$webhook" ]]; then
        if [[ "$webhook" != https://* ]]; then
            echo "install.sh: webhook must start with https:// - keeping the placeholder" >&2
        else
            tmp="$(umask 077 && mktemp "$CONF_DIR/.config.XXXXXX")"
            # Passed through the environment, never on a command line.
            WEBHOOK="$webhook" awk '
                /^[[:space:]]*webhook_url[[:space:]]*=/ { print "webhook_url = " ENVIRON["WEBHOOK"]; next }
                { print }
            ' "$CONF" > "$tmp"
            install -m 600 -o root -g root "$tmp" "$CONF"
            rm -f "$tmp"
            echo "Webhook saved to $CONF"
        fi
    fi
    unset webhook
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
dropin_content="[Timer]
OnBootSec=
OnBootSec=${interval}min
OnUnitActiveSec=
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
    # Apply the new interval. If the host has been up longer than one interval,
    # systemd fires the first heartbeat right away.
    systemctl restart hostwatch-heartbeat.timer
else
    # No-op when already active, so an unchanged re-run sends nothing.
    systemctl start hostwatch-heartbeat.timer
fi

echo "Enabling login hook"
pam-auth-update --package --enable hostwatch

echo
echo "Done. Send a test message with:  sudo hostwatch test"
