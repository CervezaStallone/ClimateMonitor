#!/usr/bin/env bash
# Stop and remove the XY-MD02 WebApp service. Data (database, settings) is kept.
#
# Usage: sudo ./deploy/linux/uninstall-service.sh
set -euo pipefail

SERVICE=xy-md02
UNIT_FILE="/etc/systemd/system/${SERVICE}.service"

[ "$(id -u)" -eq 0 ] || { echo "✗ Run with sudo: sudo $0" >&2; exit 1; }

systemctl disable --now "$SERVICE" 2>/dev/null || true
rm -f "$UNIT_FILE"
systemctl daemon-reload
echo "✓ Service '$SERVICE' removed. The app folder and its data were not touched."
