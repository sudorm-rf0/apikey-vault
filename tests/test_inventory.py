import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, tmp_path, env_extra=None):
    env = dict(os.environ)
    env["APIVAULT_DIR"] = str(tmp_path)
    env["APIVAULT_PASSWORD"] = "master-pw"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "apivault", "--dir", str(tmp_path), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
    )


def inventory_run(config_dir, mapping, tmp_path, *, as_json=False):
    args = ["inventory", "--config", str(config_dir), "--mapping", str(mapping)]
    if as_json:
        args.append("--json")
    return run(args, tmp_path)


def write_mapping(path, mapping):
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def test_inventory_reports_known_references_without_values(tmp_path):
    config_dir = tmp_path / "mcp"
    config_dir.mkdir()
    sentinel = "SENTINEL-DO-NOT-PRINT-123"
    (config_dir / "claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "command": "/bin/fake-github",
                        "args": ["--token", sentinel],
                        "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
                    },
                    "remote": {
                        "type": "http",
                        "url": "https://example.test/mcp",
                        "headers": {"Authorization": "Bearer ${GITHUB_TOKEN}"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "codex.toml").write_text(
        """
[mcp_servers.docs]
command = "node"
args = ["server.js"]
cwd = "/tmp/docs"
env_vars = ["DOCS_TOKEN"]

[mcp_servers.cloud]
command = "cloud"
env = { CLOUDFLARE_API_TOKEN = "${CLOUDFLARE_API_TOKEN}" }
""".lstrip(),
        encoding="utf-8",
    )
    mapping = write_mapping(
        tmp_path / "mapping.json",
        {
            "GITHUB_TOKEN": "github-token",
            "DOCS_TOKEN": "docs-token",
            "CLOUDFLARE_API_TOKEN": "cloudflare-token",
        },
    )

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 0, r.stderr
    assert "github-token" in r.stdout
    assert "docs-token" in r.stdout
    assert "cloudflare-token" in r.stdout
    assert "unknown" in r.stdout
    assert sentinel not in r.stdout
    assert sentinel not in r.stderr


def test_inventory_rejects_symlink_escape(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    (config_dir / "linked.json").symlink_to(outside)
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "symbolic links" in r.stderr
    assert str(outside) not in r.stderr


def test_inventory_rejects_path_traversal_in_mapping(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    mapping = write_mapping(tmp_path / "mapping.json", {"../../escape": "escape-token"})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "mapping names" in r.stderr


def test_inventory_does_not_run_commands_or_touch_vault(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "claude.json").write_text(
        json.dumps({"mcpServers": {"bad": {"command": "definitely-not-run"}}}),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})
    vault_dir = tmp_path / "vault"

    r = inventory_run(config_dir, mapping, vault_dir)

    assert r.returncode == 0, r.stderr
    assert not vault_dir.exists()


def test_inventory_requires_explicit_config_and_mapping(tmp_path):
    r = run(["inventory"], tmp_path)

    assert r.returncode == 2
    assert "--config" in r.stderr and "--mapping" in r.stderr


def test_inventory_supports_current_codex_env_and_bearer_forms(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "codex.toml").write_text(
        """
[mcp_servers.remote]
url = "https://example.test/mcp"
bearer_token_env_var = "REMOTE_TOKEN"
env_http_headers = { "X-API-Key" = "API_TOKEN" }

[mcp_servers.sourced]
command = "server"
env_vars = [
  "LEGACY_TOKEN",
  { name = "LOCAL_TOKEN", source = "local" },
  { name = "REMOTE_SOURCE_TOKEN", source = "remote" },
]
args = ["--token=${ARG_TOKEN}", "ordinary"]
http_headers = { Authorization = "Bearer ${HEADER_TOKEN}" }
""".lstrip(),
        encoding="utf-8",
    )
    mapping = write_mapping(
        tmp_path / "mapping.json",
        {
            "REMOTE_TOKEN": "remote",
            "API_TOKEN": "api",
            "LEGACY_TOKEN": "legacy",
            "LOCAL_TOKEN": "local",
            "REMOTE_SOURCE_TOKEN": "remote-source",
            "ARG_TOKEN": "arg",
            "HEADER_TOKEN": "header",
        },
    )

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["summary"]["files_scanned"] == 1
    assert report["summary"]["consumers"] == 7
    assert not report["unknown"]
    sources = {item["source"] for item in report["consumers"]}
    assert "bearer_token_env_var" in sources
    assert "env_http_headers.X-API-Key" in sources
    assert "args[0]" in sources
    assert "http_headers.Authorization" in sources
    assert {item["restart"] for item in report["consumers"]} == {"unknown"}


def test_inventory_reports_unsupported_formats_and_project_servers(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "cursor.jsonc").write_text('{"mcpServers": {}}', encoding="utf-8")
    (config_dir / "claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {},
                "projects": {
                    "/tmp/project": {
                        "mcpServers": {"project-only": {"command": "npx"}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    reasons = " ".join(item["reason"] for item in report["unknown"])
    assert "unsupported config format .jsonc" in reasons
    assert "project-scoped mcpServers are unsupported" in reasons


def test_inventory_recognizes_claude_variable_defaults(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote": {
                        "type": "http",
                        "url": "${API_BASE_URL:-https://api.example.test}/mcp",
                        "headers": {"Authorization": "Bearer ${API_KEY:-local}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {"API_KEY": "api"})

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert [item["credential"] for item in report["consumers"]] == ["api"]
    assert not report["unknown"]


def test_inventory_ignores_non_credential_literals(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "files": {
                        "command": "npx",
                        "args": ["server", "--root", "/tmp/project"],
                        "env": {"LOG_LEVEL": "debug", "CODEX_CLI_PATH": "/tmp/codex"},
                        "headers": {"X-Trace": "on"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["unknown"] == []
    assert report["consumers"] == []


def test_inventory_rejects_mapping_label_injection(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    mapping = write_mapping(tmp_path / "mapping.json", {"TOKEN": "safe | forged"})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "table delimiters" in r.stderr


def test_inventory_rejects_symlinks_even_when_inside_config_root(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    target = config_dir / "real.json"
    target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    (config_dir / "alias.json").symlink_to(target)
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "symbolic links" in r.stderr


def test_inventory_rejects_oversized_config_before_emitting_content(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    sentinel = "SENTINEL-OVERSIZE"
    (config_dir / "large.json").write_text(
        json.dumps({"mcpServers": {}, "padding": sentinel + "x" * 1_048_576}),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "exceeds" in r.stderr
    assert sentinel not in r.stdout + r.stderr


def test_inventory_parse_error_does_not_echo_config_content(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    sentinel = "SENTINEL-MALFORMED-CONFIG"
    (config_dir / "broken.json").write_text(
        '{"mcpServers": {' + sentinel,
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "cannot parse JSON config" in r.stderr
    assert sentinel not in r.stdout + r.stderr

def test_inventory_deduplicates_env_vars_and_env_alias(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "codex.toml").write_text(
        """
[mcp_servers.same]
command = "server"
env_vars = ["API_KEY"]
env = { API_KEY = "${API_KEY}" }
""".lstrip(),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {"API_KEY": "api"})

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["summary"]["consumers"] == 1
    assert report["consumers"][0]["source"] == "env_vars"

def test_inventory_missing_config_file_fails_closed_without_values(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "missing.json").symlink_to(config_dir / "no-such-file.json")
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "symbolic links" in r.stderr

def test_inventory_reports_missing_mapping_as_unknown_without_echoing_literal(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    sentinel = "SENTINEL-LITERAL-VALUE"
    (config_dir / "claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote": {
                        "type": "http",
                        "url": "https://example.test/mcp",
                        "headers": {"Authorization": f"Bearer {sentinel}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["summary"]["consumers"] == 0
    assert report["summary"]["unknown"] == 1
    assert "literal header Authorization" in report["unknown"][0]["reason"]
    assert sentinel not in r.stdout + r.stderr

def test_inventory_rejects_invalid_utf8_without_echoing_bytes(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    sentinel = b"SENTINEL-BINARY-CONFIG"
    (config_dir / "broken.json").write_bytes(b'{"mcpServers": {"x": "' + sentinel + b'\xff"}}')
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path)

    assert r.returncode == 2
    assert "UTF-8" in r.stderr
    assert sentinel.decode() not in r.stdout + r.stderr

def test_inventory_reports_missing_mapping_entry_without_echoing_value(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    sentinel = "SENTINEL-VALUE-FROM-ENV"
    (config_dir / "claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote": {
                        "command": "server",
                        "env": {"MISSING_TOKEN": f"literal-{sentinel}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mapping = write_mapping(tmp_path / "mapping.json", {})

    r = inventory_run(config_dir, mapping, tmp_path, as_json=True)

    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["summary"]["unknown"] == 1
    assert "literal env MISSING_TOKEN" in report["unknown"][0]["reason"]
    assert sentinel not in r.stdout + r.stderr
