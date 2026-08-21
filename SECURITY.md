# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities privately — do **not** open a public
issue. Email the maintainer or open a private advisory on GitHub:

- GitHub: create a [private security advisory](https://github.com/sudorm-rf0/apikey-vault/security/advisories/new)
- Email: xrf0521@outlook.com

Include:
- Affected version / commit
- Steps to reproduce
- Impact description
- (optional) suggested fix

You should receive a response within 72 hours. Please do not disclose the issue
publicly until it has been addressed.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.6.x  | ✅ |
| < 0.6  | ❌ |

## Security model

- Secrets are encrypted with AES-256-GCM; the master password is derived via
  scrypt and is **never stored**.
- The vault file (`vault.db`) is ciphertext — it is safe to back up, sync via
  a private git repo, or move between devices.
- The local server binds to `127.0.0.1` by default; exposing it to a network
  (`--host 0.0.0.0`) is the operator's responsibility (use a strong token).
- We assume the host running the vault is trusted (we do not defend against
  keyloggers or memory reads while unlocked).
