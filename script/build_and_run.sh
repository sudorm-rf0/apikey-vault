#!/usr/bin/env bash
# Build and run the native macOS app (SwiftUI + Liquid Glass).
#
#   ./script/build_and_run.sh            # kill + build + launch
#   ./script/build_and_run.sh --verify   # launch and confirm the process
#   ./script/build_and_run.sh --logs     # launch and stream unified logs
#
# The .app bundle embeds a Python virtualenv (apivault + cryptography) so it
# runs standalone. Vault data lives in ~/.apikey-vault, shared with the CLI.
set -euo pipefail

MODE="${1:-run}"
APP_NAME="apikey-vault"
BUNDLE_ID="dev.apikeyvault.app"
MIN_SYSTEM_VERSION="15.0"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAC_DIR="$ROOT_DIR/macos"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_BINARY="$APP_MACOS/$APP_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
VENV="$APP_CONTENTS/Resources/venv"

# 1) stop any running instance and leftover backend processes
pkill -x "$APP_NAME" >/dev/null 2>&1 || true
pkill -f "apivault serve" >/dev/null 2>&1 || true

# 2) build the Swift package
cd "$MAC_DIR"
swift build -c release

# 3) stage a fresh .app bundle
python3 - "$APP_BUNDLE" <<'PY'
import shutil, sys
shutil.rmtree(sys.argv[1], ignore_errors=True)
import os
os.makedirs(sys.argv[1], exist_ok=True)
PY
mkdir -p "$APP_MACOS" "$APP_CONTENTS/Resources"
BUILD_BINARY="$(swift build -c release --show-bin-path)/$APP_NAME"
cp "$BUILD_BINARY" "$APP_BINARY"
chmod +x "$APP_BINARY"
if [ -f "$MAC_DIR/Resources/AppIcon.icns" ]; then
  cp "$MAC_DIR/Resources/AppIcon.icns" "$APP_CONTENTS/Resources/AppIcon.icns"
fi

cat >"$INFO_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleName</key>
  <string>apikey-vault</string>
  <key>CFBundleDisplayName</key>
  <string>apikey-vault</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.6.0</string>
  <key>CFBundleVersion</key>
  <string>0.6.0</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>
  <string>$MIN_SYSTEM_VERSION</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

# 4) embed the Python backend venv (create once; ~10s on first build)
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Creating embedded Python venv (one-time)"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip >/dev/null
  "$VENV/bin/pip" install --quiet "$ROOT_DIR"
fi

open_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

case "$MODE" in
  run)
    open_app
    echo "Launched $APP_BUNDLE"
    ;;
  build|--build)
    echo "Built $APP_BUNDLE (not launched)"
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    open_app
    sleep 3
    if pgrep -x "$APP_NAME" >/dev/null; then
      echo "OK: $APP_NAME is running"
    else
      echo "FAIL: $APP_NAME did not stay running" >&2
      exit 1
    fi
    ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
