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
LAST_ALIVE_SERVICE=/etc/systemd/system/hostwatch-last-alive.service
LAST_ALIVE_TIMER=/etc/systemd/system/hostwatch-last-alive.timer
LAST_ALIVE_DROPIN_DIR=/etc/systemd/system/hostwatch-last-alive.timer.d
PAM_PROFILE=/usr/share/pam-configs/hostwatch
CONF_DIR=/etc/hostwatch
STATE_DIR=/var/lib/hostwatch
LEDGER=uptime.json
PAM_SESSION=/etc/pam.d/common-session
PAM_HOOK_RE='pam_exec\.so.*/usr/local/bin/hostwatch login'

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
fi
# pam-auth-update silently leaves a hand-edited common-session unchanged. Stop
# here, before anything is removed, so logins never exec a missing program.
if grep -Eq "$PAM_HOOK_RE" "$PAM_SESSION" 2>/dev/null; then
    cat >&2 <<EOF
uninstall.sh: the login hook is still in $PAM_SESSION (pam-auth-update does
not change a hand-edited file). Nothing was removed. Delete this line by hand,
then run uninstall.sh again:

    session optional pam_exec.so quiet /usr/local/bin/hostwatch login
EOF
    exit 1
fi
rm -f "$PAM_PROFILE"

# Every disable runs even when the unit file is already gone; the enablement
# links it then cannot find are removed below.
echo "Removing shutdown notification"
# Stopping it runs its ExecStop, which sends nothing because the system is
# not shutting down.
systemctl disable --now hostwatch-shutdown.service || true

echo "Removing heartbeat"
systemctl disable --now hostwatch-heartbeat.timer || true
systemctl stop hostwatch-heartbeat.service || true

echo "Removing last-alive timer"
systemctl disable --now hostwatch-last-alive.timer || true
systemctl stop hostwatch-last-alive.service || true

echo "Removing boot notification"
# --now: a boot notification that is still retrying must not send afterwards.
systemctl disable --now hostwatch-boot.service || true

rm -f "$UNIT" "$SHUTDOWN_UNIT" "$HEARTBEAT_TIMER" "$HEARTBEAT_SERVICE" \
    "$LAST_ALIVE_TIMER" "$LAST_ALIVE_SERVICE"
rm -rf "$HEARTBEAT_DROPIN_DIR" "$LAST_ALIVE_DROPIN_DIR"
rm -f /etc/systemd/system/multi-user.target.wants/hostwatch-boot.service \
    /etc/systemd/system/multi-user.target.wants/hostwatch-shutdown.service \
    /etc/systemd/system/timers.target.wants/hostwatch-heartbeat.timer \
    /etc/systemd/system/timers.target.wants/hostwatch-last-alive.timer
systemctl daemon-reload
for unit in hostwatch-boot.service hostwatch-shutdown.service \
        hostwatch-heartbeat.service hostwatch-heartbeat.timer \
        hostwatch-last-alive.service hostwatch-last-alive.timer; do
    systemctl reset-failed "$unit" 2>/dev/null || true
done

echo "Removing program files"
rm -f "$BIN"
# The boot-session ledger is the admin's usage history, not an installed
# program file: ask before it goes, defaulting to "keep" when there is no
# terminal to ask on (a non-interactive run, e.g. from a script).
keep_ledger=0
if [[ -e "$STATE_DIR/$LEDGER" ]]; then
    if [[ -t 0 ]]; then
        read -r -p "Delete the boot-session uptime history ($STATE_DIR/$LEDGER)? [y/N] " answer \
            || answer=""
        case "$answer" in
            y|Y|yes|Yes|YES) keep_ledger=0 ;;
            *) keep_ledger=1 ;;
        esac
    else
        keep_ledger=1
    fi
fi
rm -rf "$LIB_DIR"
if [[ $keep_ledger -eq 1 ]]; then
    find "$STATE_DIR" -mindepth 1 ! -name "$LEDGER" -exec rm -rf {} + 2>/dev/null || true
    echo "Kept $STATE_DIR/$LEDGER (remove it by hand if you no longer want it)"
else
    rm -rf "$STATE_DIR"
fi

if [[ $purge -eq 1 ]]; then
    echo "Removing $CONF_DIR"
    rm -rf "$CONF_DIR"
elif [[ -d "$CONF_DIR" ]]; then
    echo "Kept $CONF_DIR (use --purge to remove it)"
fi

echo "Done."
