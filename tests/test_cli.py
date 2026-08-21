import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, tmp_path, password="master-pw", env_extra=None, stdin=None):
    env = dict(os.environ)
    env["APIVAULT_DIR"] = str(tmp_path)
    env["APIVAULT_PASSWORD"] = password
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "apivault", "--dir", str(tmp_path), *args],
        capture_output=True,
        text=True,
        input=stdin,
        env=env,
        cwd=ROOT,
    )


def test_full_flow(tmp_path):
    r = run(["init"], tmp_path)
    assert r.returncode == 0, r.stderr

    r = run(["store", "OPENAI_API_KEY", "--value", "sk-abc"], tmp_path)
    assert r.returncode == 0, r.stderr

    r = run(["get", "OPENAI_API_KEY"], tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "sk-abc"

    r = run(["list"], tmp_path)
    assert "OPENAI_API_KEY" in r.stdout

    r = run(["list", "--json"], tmp_path)
    data = json.loads(r.stdout)
    assert data[0]["name"] == "OPENAI_API_KEY"
    assert "value" not in json.dumps(data)

    r = run(["export-env"], tmp_path)
    assert "export OPENAI_API_KEY='sk-abc'" in r.stdout or "export OPENAI_API_KEY=sk-abc" in r.stdout

    r = run(["delete", "OPENAI_API_KEY", "--yes"], tmp_path)
    assert r.returncode == 0
    r = run(["get", "OPENAI_API_KEY"], tmp_path)
    assert r.returncode == 1
    assert "not found" in r.stderr


def test_store_via_stdin_strips_newline(tmp_path):
    run(["init"], tmp_path)
    r = run(["store", "K", "--stdin"], tmp_path, stdin="secret-value\n")
    assert r.returncode == 0, r.stderr
    r = run(["get", "K"], tmp_path)
    assert r.stdout.strip() == "secret-value"


def test_wrong_password(tmp_path):
    run(["init"], tmp_path)
    r = run(["get", "K"], tmp_path, password="wrong")
    assert r.returncode == 1
    assert "wrong master password" in r.stderr


def test_export_env_quotes_safely(tmp_path):
    import shlex

    run(["init"], tmp_path)
    run(["store", "WEIRD", "--value", "a'b c"], tmp_path)
    r = run(["export-env"], tmp_path)
    assert r.returncode == 0
    assert f"export WEIRD={shlex.quote(chr(97) + chr(39) + chr(98) + chr(32) + chr(99))}" in r.stdout


def test_change_password_requires_old_and_new(tmp_path):
    run(["init"], tmp_path)
    run(["store", "K", "--value", "v1"], tmp_path)
    r = run(
        ["change-password", "--new-password-stdin"],
        tmp_path,
        password="master-pw",
        stdin="new-pw",
    )
    assert r.returncode == 0, r.stderr

    # old password rejected
    r = run(["get", "K"], tmp_path, password="master-pw")
    assert r.returncode == 1
    # new password works
    r = run(["get", "K"], tmp_path, password="new-pw")
    assert r.stdout.strip() == "v1"


def test_init_twice_fails(tmp_path):
    assert run(["init"], tmp_path).returncode == 0
    r = run(["init"], tmp_path)
    assert r.returncode == 1
    assert "already exists" in r.stderr


def test_status(tmp_path):
    r = run(["status"], tmp_path)
    assert r.returncode == 0
    assert "initialized: no" in r.stdout
    run(["init"], tmp_path)
    r = run(["status"], tmp_path)
    assert "initialized: yes" in r.stdout
