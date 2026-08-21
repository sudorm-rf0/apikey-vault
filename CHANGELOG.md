# Changelog

## 0.5.0 (2026-08-21)

### Security & robustness
- **Auto-lock after inactivity** (15 min) in both the web GUI and the native macOS app.
- **Import now backs up the current vault first** (`vault.db.backup-<timestamp>`, keeps 5) so a bad import can never destroy data.
- Fixed SQLite URI quoting so vaults in paths containing spaces/special characters import correctly.
- Browser extension: configurable vault server URL (any localhost port) in the options page.
- Browser extension: pasted redaction is inserted at the caret position instead of appended.
- Native app ships a real app icon (`.icns`).

### Chores
- Unified version to 0.5.0 across Python, Swift, and the extension.
- `script/test.sh` runs the full test suite (pytest + pattern tests + Swift self-test).
- Added `CHANGELOG.md`.

## 0.4.0 (2026-08-21)

### Key Guard — stop plaintext keys from reaching AI chats
- Web GUI & native app: Copy now puts the safe placeholder `{{NAME}}`; plaintext copy requires an explicit warning dialog; native app clears the clipboard after 30 s; Reveal shows an on-screen warning.
- Browser extension (Chrome/Edge MV3): detects common API key formats in any input, blocks pastes (→ `{{REDACTED}}`) and redacts typing live, with a warning toast; optional vault integration resolves matches to `{{vault:NAME}}`.
- AGENTS.md instructs agents to use `apivault get` / placeholders instead of asking users to paste plaintext.

## 0.3.0 (2026-08-21)

### Native macOS app (Apple design)
- SwiftUI app following Apple HIG / Liquid Glass (system materials, adaptive light/dark, native split view + toolbar).
- App auto-spawns the embedded Python backend (bundled venv), connects on localhost, stops it on quit.
- `script/build_and_run.sh` (kill + build + stage `.app` + launch) and Codex Run-button bootstrap.
- `apikey-vault-selftest` verifies the full API round trip against the real backend.

## 0.2.0 (2026-08-21)

### Graphical web UI + multi-device + standalone
- Web GUI: lock gate, key library, add/edit/reveal/copy, key paste box (multi-line `NAME=value`), change password, encrypted export/import, first-run init.
- Multi-device: `--host 0.0.0.0` LAN access; encrypted vault export/import (safe cross-device transfer).
- New API: `/v1/init`, `/v1/password`, `/v1/export`, `/v1/import`; static tokens survive Lock.
- `serve --open` and `scripts/build_app.sh` standalone web bundle.

## 0.1.0 (2026-08-21)

### Initial release
- Local encrypted API-key vault for AI agents (AES-256-GCM + scrypt, master password never stored).
- CLI: init/store/get/list/info/delete/rename/export-env/change-password/serve.
- HTTP API with bearer-token auth and unlock rate limiting.
