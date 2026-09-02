#!/bin/bash
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/Vellium Tweaker.app"

if [ ! -d "$APP" ]; then
  osascript -e 'display alert "Vellium Tweaker not found" message "Keep this opener beside Vellium Tweaker.app, then try again." as critical'
  exit 1
fi

# GitHub artifacts are not notarized, so browsers attach a quarantine marker.
# Remove it only from this downloaded application and launch the bundle.
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
open "$APP"
