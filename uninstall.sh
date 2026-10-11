#!/usr/bin/env bash
# Remove HostWatch. Keeps /etc/hostwatch unless --purge is given.
#
#   sudo ./uninstall.sh [--purge]
set -euo pipefail

LIB_DIR=/usr/local/lib/hostwatch
BIN=/usr/local/bin/hostwatch
UNIT=/etc/systemd/system/hostwatch-boot.service
SHUTDOWN_UNIT=/etc/systemd/system/hostwatch-shutdown.service
HEARTBEAT_SERVICE=/etc/systemd/system/hostwatch-heartbeat.service
HEARTBEAT_TIMER=/etc/systemd/system/hostwatch-heartbeat.timer
HEARTBEAT_DROPIN_DIR=/etc/systemd/system/hostwatch-heartbeat.timer.d
PAM_PROFILE=/usr/share/pam-configs/hostwatch
CONF_DIR=/etc/hostwatch
STATE_DIR=/var/lib/hostwatch

purge=0
case "${1:-}" in
    "") ;;
    --purge) purge=1 ;;
    *) echo "usage: $0 [--purge]" >&2; exit 2 ;;
esac

if [[ $EUID -ne 0 ]]; then
    echo "uninstall.sh: must be run as root (try: sudo $0)" >&2
    exit 1
fi

# Take the hook out of the PAM stack before removing the program it runs.
if [[ -e "$PAM_PROFILE" ]]; then
    echo "Removing login hook"
    pam-auth-update --package --remove hostwatch
    rm -f "$PAM_PROFILE"
fi

# Stopping it runs its ExecStop, which sends nothing because the system is
# not shutting down.
if [[ -e "$SHUTDOWN_UNIT" ]]; then
    echo "Removing shutdown notification"
    systemctl disable --now hostwatch-shutdown.service || true
    rm -f "$SHUTDOWN_UNIT"
fi

if [[ -e "$HEARTBEAT_TIMER" || -e "$HEARTBEAT_SERVICE" || -d "$HEARTBEAT_DROPIN_DIR" ]]; then
    echo "Removing heartbeat"
    systemctl disable --now hostwatch-heartbeat.timer || true
    systemctl stop hostwatch-heartbeat.service || true
    rm -f "$HEARTBEAT_TIMER" "$HEARTBEAT_SERVICE"
    rm -rf "$HEARTBEAT_DROPIN_DIR"
fi

if [[ -e "$UNIT" ]]; then
    echo "Removing boot notification"
    systemctl disable hostwatch-boot.service || true
    rm -f "$UNIT"
fi
systemctl daemon-reload

echo "Removing program files"
rm -f "$BIN"
rm -rf "$LIB_DIR" "$STATE_DIR"

if [[ $purge -eq 1 ]]; then
    echo "Removing $CONF_DIR"
    rm -rf "$CONF_DIR"
elif [[ -d "$CONF_DIR" ]]; then
    echo "Kept $CONF_DIR (use --purge to remove it)"
fi

echo "Done."
