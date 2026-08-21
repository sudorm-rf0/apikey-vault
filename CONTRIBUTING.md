# Contributing to apikey-vault

Thanks for your interest! This is a security-sensitive project, so please read
the whole guide before opening issues or pull requests.

## Project layout

```
apivault/            Python package: CLI + HTTP API + encrypted storage + web GUI
macos/               Native macOS app (SwiftUI, APIVaultCore / APIVaultApp / SelfTest)
extension/           Key Guard browser extension (Chrome/Edge, MV3)
tests/               pytest suite + Key Guard pattern tests
script/              build/run/test entrypoints for the native app
scripts/             packaging helpers (web bundle, extension zip)
docs/                API reference, screenshots
```

## Development setup

```bash
pip install -e ".[dev]"
python -m pytest                       # Python + storage + API tests
node tests/test_patterns.js            # Key Guard pattern tests
./script/test.sh                       # everything (Python + patterns + Swift)
```

## Security considerations

- Never put real keys, tokens, or credentials in code, tests, or screenshots.
- The storage format (`nonce || AES-256-GCM ciphertext || tag`) and KDF
  parameters in `apivault/crypto.py` must not be changed casually — they affect
  compatibility with existing vaults.
- New API endpoints must follow the existing auth model (bearer token,
  `Cache-Control: no-store`, no secret logging).
- Web GUI strings must stay free of inline styles/scripts (CSP is strict).

## Pull requests

1. Keep changes focused; one logical change per PR.
2. Add or update tests for every behavior change.
3. Run `./script/test.sh` locally before pushing.
4. Describe what changed and why; mention any security implications.

## Issues

Use the issue templates. For security vulnerabilities, do **not** open a public
issue — follow [SECURITY.md](SECURITY.md).
