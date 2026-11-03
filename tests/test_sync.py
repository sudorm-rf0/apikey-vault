import os
import subprocess
import sys

import pytest

from apivault import sync as vault_sync
from apivault.store import VaultStore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, tmp_path, password=None, env_extra=None, stdin=None):
    env = dict(os.environ)
    env["APIVAULT_DIR"] = str(tmp_path)
    if password:
        env["APIVAULT_PASSWORD"] = password
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "apivault", "--dir", str(tmp_path), *args],
        capture_output=True, text=True, input=stdin, env=env, cwd=ROOT,
    )


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Give the temp-repo commits a deterministic identity.

    CI runners have no global git identity, which makes ``git commit`` fail
    with "Author identity unknown". The sync code inherits the environment,
    so these variables reach both the CLI subprocesses and the in-process
    server test without touching the user's git config.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "API Vault Tests")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tests@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "API Vault Tests")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "tests@example.invalid")


@pytest.fixture()
def bare_repo(tmp_path):
    repo = tmp_path / "repo.git"
    subprocess.run(["git", "init", "-q", "--bare", str(repo)], check=True)
    # Sync uses ``main`` as the remote branch; pin the bare repo's default
    # branch instead of relying on the host's init.defaultBranch setting.
    subprocess.run(
        ["git", "--git-dir", str(repo), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
    )
    return str(repo)


def test_cli_sync_push_pull_roundtrip(tmp_path, bare_repo):
    src = tmp_path / "src"
    dst = tmp_path / "dst"

    run(["init"], src, password="pw")
    run(["store", "MY_KEY", "--value", "sk-sync-value"], src, password="pw")

    r = run(["sync", "push", "--repo", bare_repo], src, password="pw")
    assert r.returncode == 0, r.stderr
    assert "pushed" in r.stderr

    r = run(["sync", "push", "--repo", bare_repo], src, password="pw")
    assert r.returncode == 0
    assert "already up to date" in r.stderr

    r = run(["sync", "pull", "--repo", bare_repo, "--yes"], dst)
    assert r.returncode == 0, r.stderr
    assert "pulled" in r.stderr

    r = run(["get", "MY_KEY"], dst, password="pw")
    assert r.returncode == 0
    assert r.stdout.strip() == "sk-sync-value"


def test_cli_sync_status(tmp_path, bare_repo):
    src = tmp_path / "src"
    run(["init"], src, password="pw")
    run(["store", "K", "--value", "v"], src, password="pw")
    run(["sync", "push", "--repo", bare_repo], src, password="pw")

    r = run(["sync", "status", "--repo", bare_repo], src)
    assert r.returncode == 0, r.stderr
    assert "ahead/behind:  0/0" in r.stdout
    assert "remote vault:  yes" in r.stdout


def test_cli_sync_requires_repo(tmp_path):
    src = tmp_path / "src"
    run(["init"], src, password="pw")
    r = run(["sync", "push"], src, password="pw")
    assert r.returncode == 1
    assert "APIVAULT_SYNC_REPO" in r.stderr


def test_sync_via_env_repo(tmp_path, bare_repo):
    src = tmp_path / "src"
    run(["init"], src, password="pw")
    run(["store", "K", "--value", "v"], src, password="pw")
    r = run(["sync", "push"], src, password="pw", env_extra={"APIVAULT_SYNC_REPO": bare_repo})
    assert r.returncode == 0, r.stderr


def test_doctor(tmp_path):
    run(["init"], tmp_path, password="pw")
    r = run(["doctor"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "vault exists" in r.stdout
    assert "python" in r.stdout
    assert "git" in r.stdout


def test_server_sync_endpoint(tmp_path, bare_repo):
    import json
    import threading
    import urllib.request

    from apivault.server import VaultHTTPServer

    store = VaultStore(tmp_path / "vault")
    store.initialize("pw")
    httpd = VaultHTTPServer(("127.0.0.1", 0), store)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"

        def call(method, path, body=None, token=None):
            data = json.dumps(body).encode() if body is not None else None
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read())

        # unlock
        status, body = call("POST", "/v1/unlock", {"password": "pw"})
        token = body["token"]

        # push
        status, body = call("POST", "/v1/sync", {"action": "push", "repo": bare_repo}, token=token)
        assert status == 200, body
        assert body["result"] == "pushed"

        # status
        status, body = call("POST", "/v1/sync", {"action": "status", "repo": bare_repo}, token=token)
        assert status == 200
        assert body["ahead"] == 0 and body["behind"] == 0

        # missing repo -> 400
        status, body = call("POST", "/v1/sync", {"action": "push"}, token=token)
        assert status == 400
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()
