#!/usr/bin/env bash
# Run the full apikey-vault test suite: Python, Key Guard patterns, Swift.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Python tests"
python3 -m pytest -q

echo "==> Key Guard pattern tests"
node "$ROOT_DIR/tests/test_patterns.js"

echo "==> Swift build + backend self-test"
cd "$ROOT_DIR/macos"
swift build -c debug >/dev/null
PYTHONPATH="$ROOT_DIR" "$(swift build --show-bin-path)/apikey-vault-selftest"

echo "==> All tests passed"
