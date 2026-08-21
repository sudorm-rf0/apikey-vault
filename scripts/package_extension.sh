#!/usr/bin/env bash
# Package the Key Guard browser extension into a distributable zip.
# The zip can be loaded via chrome://extensions (Developer mode) or uploaded
# to the Chrome Web Store / Edge Add-ons.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
mkdir -p "$DIST"
python3 - "$ROOT/extension" "$DIST/apikey-vault-guard.zip" <<'PY'
import os, shutil, sys
src, out = sys.argv[1], sys.argv[2]
if os.path.exists(out):
    os.remove(out)
shutil.make_archive(out[:-4], "zip", root_dir=src)
print("packaged:", out, f"({os.path.getsize(out)} bytes)")
PY
