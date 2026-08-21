"""Optional multi-device sync of the encrypted vault via a git repository.

The vault database is AES-256-GCM ciphertext, so committing it to a private
git repository is safe: nobody can read it without the master password.

Commands
--------
- ``push``   upload the local vault to the repo (requires unlock)
- ``pull``   download the repo's vault and replace the local one (with backup)
- ``status`` show local/remote divergence

The repository is configured with ``--repo`` or ``$APIVAULT_SYNC_REPO``. Only
``vault.db`` is tracked (via a ``.gitignore`` of ``*`` + ``!vault.db``).
Conflict policy on push: the local vault wins (last writer wins).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


class SyncError(Exception):
    """Raised when a git sync step fails."""


def default_repo() -> str | None:
    repo = os.environ.get("APIVAULT_SYNC_REPO")
    return repo.strip() if repo and repo.strip() else None


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env
    )


def _check(result: subprocess.CompletedProcess, context: str) -> None:
    if result.returncode != 0:
        raise SyncError(f"{context}: {(result.stderr or result.stdout).strip()}")


def _git_env() -> dict:
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


def worktree_dir(vault_dir: Path) -> Path:
    return vault_dir / "sync"


def _ensure_worktree(vault_dir: Path, url: str) -> Path:
    """Clone the sync repo (once) and return its worktree path."""
    work = worktree_dir(vault_dir)
    if (work / ".git").is_dir():
        return work
    vault_dir.mkdir(parents=True, exist_ok=True)
    if work.exists():
        shutil.rmtree(work)  # stale or incomplete clone
    result = _run(["clone", url, str(work)], cwd=vault_dir, env=_git_env())
    _check(result, "clone failed")
    (work / ".gitignore").write_text("*\n!vault.db\n", encoding="utf-8")
    return work


def push(vault_dir: Path, url: str, db_bytes: bytes) -> str:
    """Upload ``db_bytes`` (the encrypted vault) to the repo.

    Conflict policy: the local vault wins (last writer wins). The vault file is
    encrypted, so a lost update only means re-unlocking with the master
    password on the other device.
    """
    work = _ensure_worktree(vault_dir, url)
    env = _git_env()

    (work / "vault.db").write_bytes(db_bytes)
    (work / ".gitignore").write_text("*\n!vault.db\n", encoding="utf-8")

    _check(_run(["add", "-f", "vault.db"], work, env=env), "git add failed")

    committed = False
    result = _run(
        ["commit", "-m", f"sync vault {time.strftime('%Y-%m-%d %H:%M:%S')}"],
        work, env=env,
    )
    if result.returncode == 0:
        committed = True
    elif "nothing to commit" not in (result.stdout + result.stderr):
        _check(result, "git commit failed")

    # Integrate remote changes when the remote already has a main branch.
    has_remote = (
        _run(["rev-parse", "--verify", "origin/main"], work, env=env).returncode == 0
    )
    if has_remote:
        result = _run(["pull", "--rebase", "--autostash", "origin", "main"], work, env=env)
        if result.returncode != 0:
            porcelain = _run(["status", "--porcelain"], work, env=env).stdout
            if any(line.startswith(("UU ", "AA ")) for line in porcelain.splitlines()):
                _check(_run(["checkout", "--ours", "--", "vault.db"], work, env=env),
                       "conflict resolution failed")
                _check(_run(["add", "vault.db"], work, env=env), "git add failed")
                env2 = dict(env)
                env2["GIT_EDITOR"] = "true"
                _check(_run(["rebase", "--continue"], work, env=env2),
                       "rebase continue failed")
            else:
                _check(result, "git pull failed")

    _check(_run(["push", "-u", "origin", "HEAD"], work, env=env), "git push failed")

    return "pushed" if committed else "already up to date"


def pull(vault_dir: Path, url: str) -> Path | None:
    """Download the repo's vault.db into the worktree; return its path or None."""
    work = _ensure_worktree(vault_dir, url)
    env = _git_env()
    _check(_run(["fetch", "origin"], work, env=env), "git fetch failed")
    result = _run(["checkout", "origin/main", "--", "vault.db"], work, env=env)
    if result.returncode != 0:
        # origin/main may not have vault.db yet
        return None
    target = work / "vault.db"
    return target if target.exists() else None


def status(vault_dir: Path, url: str) -> dict:
    """Return a small status dictionary about the sync repo."""
    work = _ensure_worktree(vault_dir, url)
    env = _git_env()
    _run(["fetch", "origin"], work, env=env)

    local = _run(["rev-parse", "HEAD"], work, env=env).stdout.strip()
    remote = _run(["rev-parse", "origin/main"], work, env=env).stdout.strip()

    ahead = _run(["rev-list", "--count", "origin/main..HEAD"], work, env=env).stdout.strip()
    behind = _run(["rev-list", "--count", "HEAD..origin/main"], work, env=env).stdout.strip()

    return {
        "repo": url,
        "worktree": str(work),
        "local_commit": local,
        "remote_commit": remote if remote else None,
        "ahead": int(ahead) if ahead.isdigit() else 0,
        "behind": int(behind) if behind.isdigit() else 0,
        "has_remote_vault": (work / "vault.db").exists(),
    }
