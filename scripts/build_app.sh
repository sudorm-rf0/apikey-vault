#!/usr/bin/env bash
# Build a standalone macOS .app bundle for apikey-vault.
#
# The bundle contains its own Python virtualenv with apikey-vault installed,
# so it works without any global Python packages. It shares the vault at
# ~/.apikey-vault with the CLI.
#
# Usage:
#   ./scripts/build_app.sh [PORT]          (default port 8417)
#
# Output: dist/apikey-vault.app
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
APP_NAME="apikey-vault"
DIST="$ROOT/dist"
APP="$DIST/$APP_NAME.app"
PORT="${1:-8417}"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }

# Fresh build directory (use python for cross-platform-safe cleanup)
python3 - "$APP" "$DIST" <<'PY'
import shutil, sys
app, dist = sys.argv[1], sys.argv[2]
shutil.rmtree(app, ignore_errors=True)
import os
os.makedirs(app, exist_ok=True)
PY

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> Creating embedded virtualenv (one-time, ~10s)"
python3 -m venv "$APP/Contents/Resources/venv"
"$APP/Contents/Resources/venv/bin/pip" install --quiet --upgrade pip >/dev/null
"$APP/Contents/Resources/venv/bin/pip" install --quiet "$ROOT"

cat > "$APP/Contents/MacOS/$APP_NAME" <<LAUNCHER
#!/usr/bin/env bash
# apikey-vault launcher
RES="\$(cd "\$(dirname "\$0")/../Resources" && pwd)"
LOG="\$HOME/.apikey-vault/app.log"
mkdir -p "\$HOME/.apikey-vault"
exec "\$RES/venv/bin/python" -m apivault serve --open --port $PORT >>"\$LOG" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/$APP_NAME"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>apikey-vault</string>
  <key>CFBundleDisplayName</key><string>apikey-vault</string>
  <key>CFBundleIdentifier</key><string>dev.apikeyvault.app</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleExecutable</key><string>apikey-vault</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>MIT License</string>
</dict>
</plist>
PLIST

echo "==> Built $APP"
echo "Run it with:  open \"$APP\""
echo "Logs:         ~/.apikey-vault/app.log"
