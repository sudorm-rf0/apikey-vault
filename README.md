# 🔐 apikey-vault

> Local, encrypted API-key management for AI agents and developers — CLI, browser UI, macOS app, and local HTTP API. Keep secrets out of prompts and repositories by retrieving them only when needed.

<div align="center">

🌐 **English** | [简体中文](README.zh-CN.md)

</div>

<div align="center">

<img src="docs/banner.png" alt="apikey-vault" width="640">

[![CI](https://github.com/sudorm-rf0/apikey-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/sudorm-rf0/apikey-vault/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/sudorm-rf0/apikey-vault)](https://github.com/sudorm-rf0/apikey-vault/releases)
[![License](https://img.shields.io/github/license/sudorm-rf0/apikey-vault)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![macOS](https://img.shields.io/badge/macOS-15%2B-9cf)](script/build_and_run.sh)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

</div>

Keeping keys as plaintext in `.env` files or shell profiles is dangerous: they
can be committed to git by accident, leak into an AI agent's context, or get
scattered across machines where rotation becomes a nightmare. `apikey-vault`
stores every key encrypted with **AES-256-GCM** in a local SQLite database.
Humans manage keys through a **GUI or CLI**; agents fetch them on demand via
the CLI or a local HTTP API.

- **Web GUI** (browser single-page app, English / 中文) · **Native macOS app** (SwiftUI + Liquid Glass)
- **Key Guard browser extension** (Chrome/Edge): auto-redacts plaintext keys in AI chat inputs
- **Git multi-device sync**: sync the encrypted vault across devices via a private repo

> 30-second try: `./scripts/demo.sh` (creates a throwaway vault; never touches your real data)

## Try it safely in a disposable vault

**No real API key is needed.** The demo uses example values and a temporary vault, not your existing `~/.apikey-vault` data.

```bash
git clone https://github.com/sudorm-rf0/apikey-vault.git
cd apikey-vault
python3 -m pip install -e .
# Optional: Node.js is needed by the demo's Key Guard pattern checks.
./scripts/demo.sh
```

Requires Python 3.10+ and the `cryptography` dependency. The final demo step also needs Node.js. To start the local web UI after installation:

```bash
apivault serve --open  # localhost only by default
```

> **Security boundary:** Encryption at rest does not prevent a privileged local process or an agent that executes `apivault get` from seeing a secret. Never paste real tokens into prompts or logs. See [agent handling guidance](docs/AGENT_SECRET_HANDLING.md) and [security policy](SECURITY.md).

**Explore:** [Screenshots](#-screenshots) · [CLI usage](#-quick-start-cli) · [HTTP API](docs/API.md) · [中文说明](README.zh-CN.md) · [Issues](https://github.com/sudorm-rf0/apikey-vault/issues)

## ✨ Features

- **Graphical UI (GUI)**: browser single-page app with a lock gate, key library,
  a **paste box** (multi-line `NAME=value`, `export` prefix, quoted values, bare
  value + name), add/edit, one-click copy, reveal/hide, rename, delete, change
  password, encrypted export/import, and first-run initialization.
- **Encrypted storage**: AES-256-GCM authenticated encryption + scrypt KDF; the
  master password is **never stored**; nothing plaintext on disk.
- **CLI for humans**: `store` / `get` / `list` / `delete` / `rename` / `export-env` / `change-password` / `export` / `import`.
- **HTTP API for agents**: `apivault serve` starts a local REST service with
  bearer-token auth, bound to `127.0.0.1` by default.
- **Multi-device**: `--host 0.0.0.0` exposes the GUI to your LAN; the encrypted
  vault can be exported/imported between devices (ciphertext only), or synced
  via **git** (`apivault sync push|pull|status`).
- **Bilingual GUI**: English / 简体中文 switching, auto-lock timeout, and sync
  repo config live in the settings panel.
- **Native macOS app (Apple design)**: SwiftUI, system materials + Liquid Glass,
  adaptive light/dark, native split view and toolbar; embeds the Python backend,
  double-click to run.
- **Web standalone bundle**: `apivault serve --open` opens the GUI in your
  browser; `scripts/build_app.sh` packages `apikey-vault-web.app`.
- **Security details**: unique nonce per key; session tokens stored only as
  SHA-256 digests with TTL; unlock rate limiting; `Cache-Control: no-store` +
  CSP; vault file mode `0600`; **15-minute inactivity auto-lock** (web GUI and
  native app); **auto-backup before import** (keeps 5 `vault.db.backup-*`).
- **Minimal dependencies**: only `cryptography` at runtime; the server and GUI
  use the Python standard library plus vanilla JS.

## 📸 Screenshots

![Locked](docs/screenshot-locked.png)
![Key library (with paste box)](docs/screenshot-unlocked.png)
![Key detail](docs/screenshot-detail.png)
![Paste a key](docs/screenshot-paste.png)

> The native macOS app uses the same encrypted backend and flows (SwiftUI, following Apple HIG / Liquid Glass).

## 📦 Install

```bash
pip install -e ".[dev]"     # dev install (includes test deps)
```

Requires Python 3.10+.

## 🖥️ GUI (recommended)

```bash
apivault serve --open        # start and open http://127.0.0.1:8417 in your browser
```

- **First run**: the UI walks you through creating the vault (set a master password).
- Every launch after that: enter the master password → paste keys into the
  **Paste a key** box at the top (`OPENAI_API_KEY=sk-...`, multiple lines at
  once; `Cmd/Ctrl+Enter` saves), or use **Add key** on the left.
- The bottom bar offers **Lock / Change password / Export vault / Import vault**.

### LAN access (multi-device)

```bash
apivault serve --host 0.0.0.0 --port 8417 --token <your-agent-token>
```

Open `http://<your-ip>:8417` from a phone or another computer and connect with
**Use a bearer token instead**. Note: `--host 0.0.0.0` exposes the service to
your LAN — use a strong token and a trusted network only.

### Native macOS app (Apple design)

Built with SwiftUI and Apple's design language: system materials and Liquid
Glass, adaptive light/dark, native split-view key library and toolbar; embeds
the Python backend — no dependencies to install.

```bash
./script/build_and_run.sh          # build and launch dist/apikey-vault.app
./script/build_and_run.sh --verify # launch and confirm the process
open dist/apikey-vault.app         # or just double-click
```

- First launch shows **Initialize vault**; after that, unlock with the master password.
- Supports pasting multi-line `NAME=value` keys, reveal/copy, change password, encrypted export/import.
- Shares `~/.apikey-vault` with the CLI; backend logs to `~/.apikey-vault/app.log`.

> Requires Xcode tooling (`xcode-select --install`). For the web bundle use `./scripts/build_app.sh` (`dist/apikey-vault-web.app`).

## 🚀 Quick start (CLI)

```bash
# 1. Initialize the vault
apivault init

# 2. Store a key (interactive, --value, or --stdin)
apivault store OPENAI_API_KEY
apivault store OPENAI_API_KEY --value sk-...

# 3. Read / list / export
apivault get OPENAI_API_KEY          # value goes to stdout only (great for agents)
apivault list                        # metadata only, never values
apivault export-env                  # prints export OPENAI_API_KEY='...' lines

# 4. Move between devices (encrypted, safe)
apivault export ~/vault-backup.db    # export
apivault import ~/vault-backup.db    # import on another device (confirms with --yes)

# 5. Other
apivault info OPENAI_API_KEY
apivault rename OPENAI_API_KEY OPENAI_KEY
apivault delete OPENAI_API_KEY --yes
apivault change-password             # re-encrypts every key
apivault status
```

### Where the password comes from (priority order)

1. `--password-file <file>` (recommended for agents: a `0600` file)
2. `--password-stdin`
3. Environment variable `APIVAULT_PASSWORD`
4. Interactive `getpass` prompt

## 🤖 Using it with AI agents (three ways)

### 1. CLI (simplest)

```bash
KEY=$(apivault get OPENAI_API_KEY)   # captured in the shell; never enters the conversation
export OPENAI_API_KEY="$KEY"
```

### 2. Load all keys into the environment at once

```bash
eval "$(apivault export-env)"
```

### 3. Local HTTP API (recommended for long-running agent services)

```bash
# Terminal 1: start the service (auto-unlock with a password, or start locked and /v1/unlock later)
APIVAULT_PASSWORD='...' apivault serve --port 8417 --token my-static-agent-token

# Terminal 2 / the agent:
curl -s http://127.0.0.1:8417/v1/health
curl -s -X PUT http://127.0.0.1:8417/v1/keys/OPENAI_API_KEY \
  -H "Authorization: Bearer my-static-agent-token" \
  -H "Content-Type: application/json" \
  -d '{"value":"sk-...","description":"OpenAI key"}'
curl -s http://127.0.0.1:8417/v1/keys/OPENAI_API_KEY \
  -H "Authorization: Bearer my-static-agent-token"
```

Full API reference: [docs/API.md](docs/API.md).

## 🔄 Git multi-device sync

Commit the encrypted `vault.db` to a **private** git repository (e.g. a GitHub
private repo) to sync the key library across devices — the file is ciphertext,
so nobody can read anything without the master password.

```bash
apivault sync push --repo git@github.com:you/vault-sync.git   # upload (needs unlock)
apivault sync pull --repo git@github.com:you/vault-sync.git   # download (backs up local first)
apivault sync status --repo git@github.com:you/vault-sync.git # show divergence
```

Set `APIVAULT_SYNC_REPO` to avoid passing `--repo` every time, or configure it
in the web GUI settings panel and click Push / Pull / Status. Conflict policy:
the local vault wins (last writer wins).

## 🛠️ Diagnostics

```bash
apivault doctor    # checks Python, cryptography, git, vault state/perms, sync config
```

## 🗂️ Data location

Default: `~/.apikey-vault/vault.db` (override with `APIVAULT_DIR` or `--dir`).

- `keys` table: `name, description, payload(BLOB), created_at, updated_at`
  - `payload = nonce(12B) || AES-256-GCM ciphertext || tag(16B)`
- `meta` table: scrypt salt, verify blob, KDF params, version

## 🔒 Key Guard: keep plaintext keys out of AI chats

The whole point of this product: **keys should never appear in plaintext in an
AI chat box**. Three layers of protection:

### 1. UI layer (web GUI + native macOS app)

- **Copy defaults to a safe placeholder**: Copy puts `{{OPENAI_API_KEY}}` on the
  clipboard, not the real value — accidental pastes leak only a placeholder.
- **Plaintext copy requires confirmation**: Plaintext… shows a warning dialog
  before copying the real key, plus a reminder not to paste it into AI chats.
- **Native app auto-clears the clipboard** 30 seconds after a plaintext copy.
- **On-screen warning** when Reveal shows the real value.
- **Inactivity auto-lock**: 15 minutes without activity locks the vault (web GUI and native app).

### 2. Browser extension (Chrome / Edge, MV3)

The `extension/` directory is a ready-to-load extension that intercepts common
API key formats in **any input field on any page** (including ChatGPT, Claude,
etc.):

- Supported: `sk-` (OpenAI), `sk-ant-` (Anthropic), `ghp_`/`github_pat_` (GitHub),
  `AIza` (Google), `xoxb-` (Slack), `AKIA` (AWS), `sk_live_`/`sk_test_` (Stripe),
  JWT-style tokens, and more.
- **Paste interception**: pasted keys are blocked and replaced with `{{REDACTED}}`, with a warning toast.
- **Live typing redaction**: keys typed into a field are redacted in place.
- **Optional vault integration**: enable "Resolve keys against the local vault"
  in the extension options, set the vault URL (default `http://127.0.0.1:8417`,
  any port) and the `apivault serve --token` token; matching keys are replaced
  with `{{vault:KEY_NAME}}` so the agent can safely `apivault get KEY_NAME`.

Install: Chrome/Edge → Extensions → Developer mode → Load unpacked → select the
`extension/` folder. Distribute with `./scripts/package_extension.sh`
(`dist/apikey-vault-guard.zip`, also uploadable to the Chrome Web Store /
Edge Add-ons).

![Key Guard interception](docs/screenshot-guard.png)

### 3. Agent rules

See [AGENTS.md](AGENTS.md): agents fetch keys via `apivault get <name>` or the
`{{vault:NAME}}` placeholder — they never ask you to paste plaintext.

## 🔒 Security model

- **Threat**: vault file copied, disk lost → nothing can be recovered without the master password.
- **Assumption**: the host is trusted while running; we do not defend against keyloggers or memory reads while unlocked.
- **Design**: scrypt(N=2^17, r=8, p=1) derives a 32-byte key; AES-256-GCM
  authenticated encryption; the password is never stored — verified only by
  decrypting a fixed magic; sensitive bytes are best-effort zeroed in memory.
- Detailed plan: [PLAN.md](PLAN.md).

## ✅ Tests

```bash
./script/test.sh        # Python tests + Key Guard pattern tests + Swift self-test
# or individually:
python -m pytest
node tests/test_patterns.js
```

Covers crypto round-trips/tampering, storage CRUD/change-password/export-import
(incl. import auto-backup), CLI end-to-end, full HTTP API (auth, rate limits,
static GUI, first-run init), Key Guard key patterns, and the Swift client ↔
real backend round trip.

## 📚 FAQ

**Where are the keys stored? Is it safe?**
`~/.apikey-vault/vault.db` by default — all AES-256-GCM ciphertext; the master
password is scrypt-derived and never stored. Even if the file is copied, nothing
can be recovered without the password.

**Why does Copy put `{{NAME}}` on the clipboard?**
By design — to stop you accidentally pasting a real key into an AI chat. For the
real value use Plaintext… (warned) or `apivault get <name>` into your environment.

**How does an agent use my keys?**
`apivault get OPENAI_API_KEY` (value only on stdout, never in the conversation),
or run `apivault serve` and let the agent call the local API. Pasting in a
browser is auto-redacted by Key Guard to `{{REDACTED}}` / `{{vault:NAME}}`.

**How do I sync between devices?**
`apivault sync push|pull --repo <private-repo>` (or one click in the web GUI).
It syncs ciphertext, so even a leaked repo is safe.

**Change password / move devices / delete a key?**
`apivault change-password`; cross-device `apivault export` / `import` (auto-backup
before import); delete with `apivault delete <name>`.

**Environment problems?**
`apivault doctor` runs a one-shot diagnostic (Python/crypto/git/vault perms/sync config).

## 🧱 Repository structure

```
apivault/            Python package: CLI + HTTP API + encrypted storage + web GUI
macos/               Native macOS app (SwiftUI: APIVaultCore / APIVaultApp / SelfTest)
extension/           Key Guard browser extension (Chrome/Edge MV3)
tests/               pytest suite + Key Guard pattern tests
script/              native-app build/run/test entrypoints
scripts/             packaging & demo helpers (web bundle, extension zip, demo)
docs/                API reference & screenshots
```

## 🗺️ Roadmap

- [x] Encrypted storage + CLI + HTTP API (v0.1)
- [x] Web GUI + LAN access + export/import (v0.2)
- [x] Native macOS app (Apple design) (v0.3)
- [x] Key Guard (UI + extension + agent rules) (v0.4)
- [x] Auto-lock / import backup / extension improvements (v0.5)
- [x] Git multi-device sync / doctor / bilingual UI / settings panel (v0.6)
- [ ] Windows/Linux standalone (Electron/Tauri)
- [ ] Publish the extension to Chrome Web Store / Edge Add-ons
- [ ] More key-format detection and custom patterns

## 🤝 Community

- Report bugs: [Issues](https://github.com/sudorm-rf0/apikey-vault/issues) (use the templates)
- Contribute: [CONTRIBUTING.md](CONTRIBUTING.md)
- Report vulnerabilities: [SECURITY.md](SECURITY.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Cite this project: [CITATION.cff](CITATION.cff)

If you find this useful, ⭐ Star the repo — it helps more developers manage API keys safely.

> Tip: `docs/banner.png` can be used as the repo's **Social preview**
> (Settings → Social preview → Upload) so shared links show the banner.

## 🛠️ Troubleshooting

- **Port in use**: the native app and `apivault serve` default to `8417`. If it
  is taken, the native app connects to the existing service (mind different vault
  paths); the CLI uses `--port`, and the extension's "Vault server URL" can be changed.
- **Extension loaded but not working**: newer Chrome/Edge disable command-line
  loaded extensions by default; install via Extensions → Developer mode → Load
  unpacked and confirm the toggle is on.
- **Clipboard/paste blocked**: macOS asks for permission on first use; allow it in
  System Settings → Privacy & Security.
- **Recover from a bad import**: imports auto-backup first; restore a file from
  `~/.apikey-vault/vault.db.backup-*` (stop the service, replace the file, restart).

## ⚠️ Notes

- Binds to `127.0.0.1` by default; `--host 0.0.0.0` exposes it to the LAN —
  evaluate the risk and keep your token safe.
- Never commit real keys; the tests in this repo use fake keys only.
- `export`/`import` replaces the vault wholesale (no merge) — make sure the
  target device has no newer local changes.

## 📄 License

MIT
