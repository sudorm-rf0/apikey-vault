#!/usr/bin/env bash
# Self-contained demo of apikey-vault. Creates a throwaway vault in a temp
# dir, stores a couple of keys, shows the CLI, the sync command, and the
# Key Guard pattern tests. Nothing is written to your real vault.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The final step runs the Key Guard pattern tests with Node.js. Check for it
# up front so a missing runtime fails fast with an actionable message instead
# of a late `node: command not found`.
if ! command -v node >/dev/null 2>&1; then
  echo "✗ Node.js is required for the demo's Key Guard pattern checks," >&2
  echo "  but no 'node' executable was found on your PATH." >&2
  echo "  Install Node.js from https://nodejs.org (macOS: 'brew install node'), then rerun:" >&2
  echo "    ./scripts/demo.sh" >&2
  echo "  No demo vault was created." >&2
  exit 1
fi

VD="$(mktemp -d /tmp/apivault-demo.XXXXXX)"
export APIVAULT_PASSWORD='demo-password'

echo "▶ init (creates encrypted vault)"
python3 -m apivault --dir "$VD" init

echo "▶ store keys (paste / value / stdin)"
python3 -m apivault --dir "$VD" store OPENAI_API_KEY --value sk-demo-1234567890abcdef
printf 'sk-ant-demo-abcdefghijklmnop\n' | python3 -m apivault --dir "$VD" store ANTHROPIC_API_KEY --stdin

echo "▶ list (metadata only, never values)"
python3 -m apivault --dir "$VD" list

echo "▶ get (value goes to stdout only)"
python3 -m apivault --dir "$VD" get OPENAI_API_KEY

echo "▶ export-env"
python3 -m apivault --dir "$VD" export-env

echo "▶ on-disk ciphertext check (no plaintext)"
if strings "$VD/vault.db" | grep -q sk-demo-; then
  echo "✗ plaintext found (this should never happen)"
  exit 1
else
  echo "✓ vault.db contains no plaintext"
fi

echo "▶ Key Guard pattern tests"
node "$ROOT/tests/test_patterns.js" | tail -1

echo
echo "Demo vault at: $VD  (delete it anytime)"
echo "Web GUI:       cd $ROOT && apivault serve --open"
echo "Docs:          https://github.com/sudorm-rf0/apikey-vault#readme"
