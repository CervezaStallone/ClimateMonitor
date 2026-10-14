#!/usr/bin/env bash
# Install the XY-MD02 WebApp as a systemd service (starts at boot, also without login).
#
# Usage (in the app folder):
#   sudo ./deploy/linux/install-service.sh            # install or update
#   sudo ./deploy/linux/install-service.sh --user pi  # run the service as another user
#   ./deploy/linux/install-service.sh --dry-run       # only show what would be done
set -euo pipefail

SERVICE=xy-md02
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT_FILE="/etc/systemd/system/${SERVICE}.service"
RUN_USER="${SUDO_USER:-}"
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --user) RUN_USER="${2:-}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

fail() { echo "✗ $*" >&2; exit 1; }
run() {
    echo "+ $*"
    if [ "$DRY_RUN" -eq 0 ]; then "$@"; fi
}

[ "$DRY_RUN" -eq 1 ] || [ "$(id -u)" -eq 0 ] || fail "Run with sudo: sudo $0"
[ -n "$RUN_USER" ] || RUN_USER="$(id -un)"
[ "$RUN_USER" != "root" ] || fail "Do not run the app as root. Use: sudo $0 --user <username>"
id "$RUN_USER" >/dev/null 2>&1 || fail "User '$RUN_USER' does not exist"
command -v systemctl >/dev/null || fail "systemd is required (systemctl not found)"

PYTHON="$(command -v python3 || true)"
[ -n "$PYTHON" ] || fail "Python 3 not found. Install it, e.g.: sudo apt install python3 python3-venv"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || fail "Python 3.10 or newer is required ($("$PYTHON" --version))"
"$PYTHON" -c 'import venv, ensurepip' 2>/dev/null \
    || fail "Python venv module missing. Install it, e.g.: sudo apt install python3-venv"

echo "→ App folder:   $APP_DIR"
echo "→ Service user: $RUN_USER"

# The service runs code from the app folder (all .py files and .venv) as RUN_USER. Nobody else may be
# able to change any of it, otherwise they could run commands as RUN_USER (e.g. via --user).
# The data folders src/ and logs/ are written by the service and are not executed.
check_tree() {
    find "$APP_DIR" \( -path "$APP_DIR/src" -o -path "$APP_DIR/logs" -o -path "$APP_DIR/.git" \) -prune -o "$@" -print -quit
}
bad="$(check_tree ! -user "$RUN_USER" ! -user root)"
[ -z "$bad" ] || fail "$bad is owned by '$(stat -c %U "$bad")'. Everything in $APP_DIR must be owned by '$RUN_USER' or root (sudo chown -R $RUN_USER '$APP_DIR')"
bad="$(check_tree -perm -o+w ! -type l)"
[ -z "$bad" ] || fail "$bad is writable by all users. Fix it with: chmod -R o-w '$APP_DIR'"

# Virtual environment and dependencies (as the service user, so it owns the files)
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    run sudo -u "$RUN_USER" "$PYTHON" -m venv "$APP_DIR/.venv"
fi
run sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip
run sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/python" -m pip install --quiet -r "$APP_DIR/requirements.txt"

# Data folder writable for the service user
run install -d -o "$RUN_USER" -g "$(id -gn "$RUN_USER")" "$APP_DIR/src"

# Serial ports (USB RS-485 dongles) are owned by the 'dialout' group (on some systems 'uucp')
for group in dialout uucp; do
    if getent group "$group" >/dev/null; then
        run usermod -aG "$group" "$RUN_USER"
        break
    fi
done

UNIT="[Unit]
Description=XY-MD02 temperature and humidity WebApp
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=\"$APP_DIR/.venv/bin/python\" \"$APP_DIR/app.py\"
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
"

echo "+ write $UNIT_FILE"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "$UNIT"
else
    printf '%s' "$UNIT" > "$UNIT_FILE"
fi
run systemctl daemon-reload
run systemctl enable "$SERVICE"
run systemctl restart "$SERVICE"

if [ "$DRY_RUN" -eq 0 ]; then
    sleep 3
    systemctl --no-pager --lines=5 status "$SERVICE" || true
    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo
    echo "✓ Installed. The app starts automatically at boot, also without login."
    echo "  Open: http://${IP:-<device-ip>}:8050   (port can be changed in the Settings tab)"
    echo "  Logs:      journalctl -u $SERVICE -f"
    echo "  Restart:   sudo systemctl restart $SERVICE"
    echo "  Uninstall: sudo $APP_DIR/deploy/linux/uninstall-service.sh"
fi
