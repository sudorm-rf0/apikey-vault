"""Command-line interface for apikey-vault.

Conventions
-----------
- ``apivault get <name>`` prints ONLY the value on stdout so agents can capture
  it with command substitution; all prompts/status go to stderr.
- The vault path is ``~/.apikey-vault`` or ``$APIVAULT_DIR``; every command
  accepts ``--dir`` to override it for that invocation (great for testing).
- Passwords: ``--password-file`` > ``--password-stdin`` > ``APIVAULT_PASSWORD``
  > interactive prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
import urllib.parse
from pathlib import Path

from apivault import __version__
from apivault import sync as vault_sync
from apivault.passwords import PasswordError, read_password
from apivault.server import DEFAULT_TTL_SECONDS, serve
from apivault.store import (
    KeyExistsError,
    KeyNotFoundError,
    VaultError,
    VaultLockedError,
    VaultNotInitializedError,
    VaultStore,
    VaultWrongPasswordError,
)


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apivault",
        description="Local, encrypted API-key vault for AI agents (Codex / Claude).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--dir", metavar="DIR", help="vault directory (default: $APIVAULT_DIR or ~/.apikey-vault)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a new vault")
    _add_password_opts(p)
    p.add_argument("--description", help="optional vault description")

    sub.add_parser("status", help="show vault status")

    p = sub.add_parser("store", help="save or update a secret")
    p.add_argument("name", help="key name, e.g. OPENAI_API_KEY")
    p.add_argument("--value", help="secret value (avoid on shared shells; prefer stdin/prompt)")
    p.add_argument("--stdin", action="store_true", help="read the value from stdin")
    p.add_argument("--description", help="optional description")
    _add_password_opts(p)

    p = sub.add_parser("get", help="print a secret value to stdout")
    p.add_argument("name", help="key name")
    _add_password_opts(p)

    p = sub.add_parser("list", help="list key names and metadata")
    p.add_argument("--json", action="store_true", help="JSON output")
    _add_password_opts(p)

    p = sub.add_parser("info", help="show metadata for one key")
    p.add_argument("name", help="key name")
    _add_password_opts(p)

    p = sub.add_parser("delete", help="delete a secret")
    p.add_argument("name", help="key name")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    _add_password_opts(p)

    p = sub.add_parser("rename", help="rename a key")
    p.add_argument("old", help="current name")
    p.add_argument("new", help="new name")
    _add_password_opts(p)

    p = sub.add_parser("export-env", help="print `export NAME='value'` lines for all keys")
    _add_password_opts(p)

    p = sub.add_parser("change-password", help="change the master password (re-encrypts everything)")
    _add_password_opts(p)
    p.add_argument("--new-password-file", metavar="FILE", help="read the NEW master password from FILE")
    p.add_argument("--new-password-stdin", action="store_true", help="read the NEW master password from stdin")

    p = sub.add_parser("serve", help="start the local HTTP API for agents")
    p.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8417, help="bind port (default 8417)")
    p.add_argument("--token", action="append", default=[], metavar="TOKEN",
                   help="static bearer token agents may use (repeatable)")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS,
                   help=f"dynamic token lifetime in seconds (default {DEFAULT_TTL_SECONDS})")
    p.add_argument("--no-unlock", action="store_true",
                   help="start locked even if a password is available")
    p.add_argument("--open", action="store_true",
                   help="open the GUI in the default browser after startup")
    _add_password_opts(p)

    # export / import for moving the (encrypted) vault between devices
    p = sub.add_parser("sync", help="sync the encrypted vault via a git repository (multi-device)")
    p.add_argument("action", choices=["push", "pull", "status"], help="push uploads; pull downloads; status reports divergence")
    p.add_argument("--repo", metavar="URL", help="git repository URL (default: $APIVAULT_SYNC_REPO)")
    p.add_argument("--yes", action="store_true", help="skip confirmation for pull")
    _add_password_opts(p)

    sub.add_parser("doctor", help="run environment diagnostics")

    p = sub.add_parser("export", help="export the encrypted vault to a file (safe to move between devices)")
    p.add_argument("file", help="output file path")
    _add_password_opts(p)

    p = sub.add_parser("import", help="replace the vault from an exported encrypted file")
    p.add_argument("file", help="input file path")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    _add_password_opts(p)

    return parser


def _add_password_opts(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("password options")
    group.add_argument("--password-file", metavar="FILE", help="read the master password from FILE")
    group.add_argument("--password-stdin", action="store_true", help="read the master password from stdin")
    group.add_argument("--confirm", action="store_true", help="ask to confirm the password (used by init/change-password)")


def _get_password(args: argparse.Namespace, prompt: str = "Master password: ") -> str:
    return read_password(
        password_file=args.password_file,
        password_stdin=args.password_stdin,
        prompt=prompt,
        confirm=getattr(args, "confirm", False),
    )


def _store(args: argparse.Namespace) -> VaultStore:
    return VaultStore(args.dir)


def _unlock_store(args: argparse.Namespace) -> VaultStore:
    store = VaultStore(args.dir)
    password = _get_password(args)
    store.unlock(password)
    return store


def _cmd_init(args: argparse.Namespace) -> int:
    store = VaultStore(args.dir)
    if store.initialized:
        _eprint(f"error: vault already exists at {store.path}")
        return 1
    password = _get_password(args, prompt="New master password: ")
    store.initialize(password, description=args.description)
    _eprint(f"vault created at {store.path}")
    _eprint("tip: store a key with `apivault store <name>`")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    store = VaultStore(args.dir)
    print(f"path:        {store.path}")
    print(f"initialized: {'yes' if store.initialized else 'no'}")
    print(f"unlocked:    {'yes' if store.unlocked else 'no'}")
    if not store.initialized:
        print("run `apivault init` to create the vault")
    return 0


def _cmd_store(args: argparse.Namespace) -> int:
    value: str | None = args.value
    if args.stdin:
        if value is not None:
            _eprint("error: use either --value or --stdin, not both")
            return 2
        value = sys.stdin.read().rstrip("\r\n")
    if value is None:
        if sys.stdin.isatty():
            value = input(f"Value for {args.name!r} (hidden? no): ")
        else:
            _eprint(f"error: no value provided; use --value, --stdin, or run interactively")
            return 2
    try:
        store = _unlock_store(args)
        try:
            existed = store.metadata(args.name)  # KeyNotFoundError if missing
        except KeyNotFoundError:
            existed = None
        store.set(args.name, value, description=args.description)
        _eprint(f"{'updated' if existed else 'stored'} {args.name!r}")
        return 0
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1


def _cmd_get(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
        print(store.get(args.name))
        store.lock()
        return 0
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
        metas = store.list()
        store.lock()
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1
    if args.json:
        print(json.dumps([{
            "name": m.name,
            "description": m.description,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        } for m in metas], indent=2))
        return 0
    if not metas:
        print("(no keys)")
        return 0
    width = max(len(m.name) for m in metas)
    for m in metas:
        desc = f"  ({m.description})" if m.description else ""
        print(f"{m.name:<{width}}  updated {m.updated_at}{desc}")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
        m = store.metadata(args.name)
        store.lock()
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1
    print(f"name:        {m.name}")
    print(f"description: {m.description or ''}")
    print(f"created_at:  {m.created_at}")
    print(f"updated_at:  {m.updated_at}")
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        try:
            answer = input(f"delete {args.name!r}? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            _eprint("aborted")
            return 1
    try:
        store = _unlock_store(args)
        store.delete(args.name)
        store.lock()
        _eprint(f"deleted {args.name!r}")
        return 0
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1


def _cmd_rename(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
        store.rename(args.old, args.new)
        store.lock()
        _eprint(f"renamed {args.old!r} -> {args.new!r}")
        return 0
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1


def _cmd_export_env(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
        metas = store.list()
        lines = []
        for m in metas:
            value = store.get(m.name)
            lines.append(f"export {m.name}={shlex.quote(value)}")
        store.lock()
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1
    print("\n".join(lines))
    return 0


def _new_password(args: argparse.Namespace) -> str:
    """Resolve the NEW password for change-password (independent of the old one)."""
    if args.new_password_file:
        try:
            value = Path(args.new_password_file).expanduser().read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise PasswordError(f"cannot read new-password file: {exc}") from exc
        if not value:
            raise PasswordError("new-password file is empty")
        return value
    if args.new_password_stdin:
        value = sys.stdin.readline().rstrip("\r\n")
        if not value:
            raise PasswordError("no new password provided on stdin")
        return value
    env_new = os.environ.get("APIVAULT_NEW_PASSWORD")
    if env_new:
        return env_new
    return read_password(
        password_file=None,
        password_stdin=False,
        prompt="New master password: ",
        confirm=True,
    )


def _cmd_change_password(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
    except (VaultError, ValueError, PasswordError) as exc:
        _eprint(f"error: {exc}")
        return 1
    try:
        new_password = _new_password(args)
    except PasswordError as exc:
        _eprint(f"error: {exc}")
        return 1
    store.change_password(new_password)
    _eprint("master password changed")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    repo = args.repo or vault_sync.default_repo()
    if not repo:
        _eprint("error: no sync repo; pass --repo <url> or set APIVAULT_SYNC_REPO")
        return 1
    store = VaultStore(args.dir)

    if args.action == "push":
        try:
            password = _get_password(args)
            store.unlock(password)
            data = store.export_bytes()
            store.lock()
        except (VaultError, ValueError, PasswordError) as exc:
            _eprint(f"error: {exc}")
            return 1
        try:
            result = vault_sync.push(store.dir, repo, data)
        except vault_sync.SyncError as exc:
            _eprint(f"error: {exc}")
            return 1
        _eprint(f"sync push: {result}")
        return 0

    if args.action == "pull":
        if not args.yes:
            try:
                answer = input(f"replace local vault from {repo}? [y/N] ").strip().lower()
            except EOFError:
                answer = "n"
            if answer not in ("y", "yes"):
                _eprint("aborted")
                return 1
        try:
            path = vault_sync.pull(store.dir, repo)
        except vault_sync.SyncError as exc:
            _eprint(f"error: {exc}")
            return 1
        if path is None:
            _eprint("nothing to pull (repo has no vault yet)")
            return 0
        try:
            store.import_bytes(path.read_bytes())
        except (VaultError, ValueError) as exc:
            _eprint(f"error: {exc}")
            return 1
        _eprint(f"pulled from {repo}; local vault replaced (backup kept) — unlock with its master password")
        return 0

    # status
    try:
        info = vault_sync.status(store.dir, repo)
    except vault_sync.SyncError as exc:
        _eprint(f"error: {exc}")
        return 1
    print(f"repo:          {info['repo']}")
    print(f"worktree:      {info['worktree']}")
    print(f"local commit:  {info['local_commit'][:12] if info['local_commit'] else '(none)'}")
    print(f"remote commit: {info['remote_commit'][:12] if info['remote_commit'] else '(none)'}")
    print(f"ahead/behind:  {info['ahead']}/{info['behind']}")
    print(f"remote vault:  {'yes' if info['has_remote_vault'] else 'no'}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    import platform
    import sqlite3

    results: list[tuple[str, str]] = []
    ok = True

    def check(name: str, passed: bool, detail: str = "", warn: bool = False) -> None:
        nonlocal ok
        status = "ok" if passed else ("warn" if warn else "FAIL")
        results.append((name, status))
        if not passed and not warn:
            ok = False
        if detail:
            results.append(("", "  " + detail))

    check("python", True, f"{platform.python_version()} ({platform.machine()})")
    try:
        import cryptography

        check("cryptography", True, cryptography.__version__)
    except Exception as exc:
        check("cryptography", False, str(exc))

    git = shutil.which("git")
    check("git", git is not None, git or "not found in PATH")

    store = VaultStore(args.dir)
    check("vault path", True, str(store.path))
    if store.initialized:
        try:
            mode = os.stat(store.path).st_mode & 0o777
            check("vault exists", True)
            check("vault perms 0600", mode == 0o600, f"actual {oct(mode)}")
        except OSError as exc:
            check("vault exists", False, str(exc))
    else:
        check("vault initialized", False, "run `apivault init`")

    repo = vault_sync.default_repo()
    check("sync repo configured", repo is not None,
          repo or "set APIVAULT_SYNC_REPO to enable multi-device sync", warn=True)

    try:
        con = sqlite3.connect(f"file:{urllib.parse.quote(str(store.path))}?mode=ro", uri=True)
        con.close()
        check("vault readable", True)
    except Exception as exc:
        check("vault readable", False, str(exc))

    print(f"{'CHECK':<20} RESULT")
    print("-" * 60)
    for name, status in results:
        if name:
            print(f"{name:<20} {status}")
        else:
            print(f"{'':<20} {status}")
    return 0 if ok else 1


def _cmd_export(args: argparse.Namespace) -> int:
    try:
        store = _unlock_store(args)
        data = store.export_bytes()
        store.lock()
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1
    out = Path(args.file).expanduser()
    try:
        out.write_bytes(data)
        os.chmod(out, 0o600)
    except OSError as exc:
        _eprint(f"error: cannot write {out}: {exc}")
        return 1
    _eprint(f"exported encrypted vault ({len(data)} bytes) to {out}")
    _eprint("import it on another device with `apivault import <file>`")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    inp = Path(args.file).expanduser()
    if not inp.is_file():
        _eprint(f"error: {inp} does not exist")
        return 1
    if not args.yes:
        try:
            answer = input(
                f"replace the current vault with {inp}? [y/N] "
            ).strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            _eprint("aborted")
            return 1
    try:
        store = VaultStore(args.dir)
        store.import_bytes(inp.read_bytes())
    except (VaultError, ValueError) as exc:
        _eprint(f"error: {exc}")
        return 1
    _eprint(f"imported {inp}; the vault is now locked — unlock with its master password")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    store = VaultStore(args.dir)
    if not store.initialized:
        _eprint(f"info: no vault at {store.path}; the GUI can create one on first run")
    elif not args.no_unlock:
        try:
            password = _get_password(args)
            store.unlock(password)
        except VaultWrongPasswordError as exc:
            _eprint(f"error: {exc}")
            return 1
        except VaultNotInitializedError as exc:
            _eprint(f"error: {exc}")
            return 1
        except PasswordError:
            _eprint("warning: no password available; server starts locked (use POST /v1/unlock)")
    try:
        serve(
            store,
            host=args.host,
            port=args.port,
            ttl_seconds=args.ttl,
            static_tokens=args.token,
            open_browser=args.open,
        )
    except KeyboardInterrupt:
        pass
    return 0


COMMANDS = {
    "init": _cmd_init,
    "status": _cmd_status,
    "store": _cmd_store,
    "get": _cmd_get,
    "list": _cmd_list,
    "info": _cmd_info,
    "delete": _cmd_delete,
    "rename": _cmd_rename,
    "export-env": _cmd_export_env,
    "change-password": _cmd_change_password,
    "sync": _cmd_sync,
    "doctor": _cmd_doctor,
    "export": _cmd_export,
    "import": _cmd_import,
    "serve": _cmd_serve,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except VaultWrongPasswordError:
        _eprint("error: wrong master password")
        return 1
    except VaultLockedError as exc:
        _eprint(f"error: {exc}")
        return 1
    except (VaultError, ValueError, PasswordError) as exc:
        _eprint(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
