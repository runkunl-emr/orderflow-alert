#!/bin/bash
# Run orderflow-alert in the background on macOS: starts at login, restarts if it stops.
#   ./install-service.sh              install or update (extra options are passed to orderflow-alert)
#   ./install-service.sh uninstall    remove
# Example: ./install-service.sh --symbol @NQ --symbol @ES
set -e
cd "$(dirname "$0")"
DIR="$PWD"
LABEL=com.orderflow-alert
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/orderflow-alert.log"

if [ "$1" = "uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed. The tool no longer runs in the background."
  exit 0
fi

[ -x .venv/bin/orderflow-alert ] || { echo "Install the tool first (README, section 4)."; exit 1; }

ARGS="<string>$DIR/.venv/bin/orderflow-alert</string><string>--no-browser</string>"
for a in "$@"; do ARGS="$ARGS<string>$a</string>"; done

mkdir -p "$HOME/Library/LaunchAgents" "$(dirname "$LOG")"
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>$ARGS</array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
XML
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. The tool runs in the background and starts at login."
echo "Panel: http://127.0.0.1:8765   Log: $LOG"
