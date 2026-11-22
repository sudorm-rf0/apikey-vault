"""Read-only inventory of explicit MCP client configuration files.

This module deliberately does not import the vault, perform network access, or
spawn processes. It reads only files under the caller-supplied config directory
and emits credential names and consumer metadata; values are never rendered.
"""

from __future__ import annotations

import json
import os
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".json", ".toml"}
UNSUPPORTED_CONFIG_SUFFIXES = {".jsonc", ".json5", ".yaml", ".yml"}
MAX_INPUT_BYTES = 1024 * 1024
CREDENTIAL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_AUTH_PREFIX = r"(?:(?:Bearer|Basic|Token)\s+)?"
_ENV_EXPANSION = r"\$\{(?P<env>[A-Za-z_][A-Za-z0-9_]*)(?:(?::?-)(?P<default>[^}]*))?\}"
_REFERENCE_RE = re.compile(
    rf"^{_AUTH_PREFIX}(?:{_ENV_EXPANSION}"
    rf"|(?:env|secret|vault):(?P<scheme>[A-Za-z_][A-Za-z0-9_]*)"
    rf"|\{{\{{vault:(?P<vault>[A-Za-z_][A-Za-z0-9_]*)\}}\}})$"
)
_EMBEDDED_REFERENCE_RE = re.compile(
    rf"{_ENV_EXPANSION}"
    r"|\{\{vault:(?P<vault>[A-Za-z_][A-Za-z0-9_]*)\}\}"
    r"|(?:^|[\s=:'\"])(?:env|secret|vault):(?P<scheme>[A-Za-z_][A-Za-z0-9_]*)"
)
_SENSITIVE_ARG_RE = re.compile(
    r"(?i)(?:^|[-_/])(?:token|api[-_]?key|secret|password|credential|bearer)(?:$|[=:])"
)
_SENSITIVE_NAME_RE = re.compile(
    r"(?i)(?:^|_)(?:TOKEN|API_KEY|ACCESS_KEY|SECRET(?:_KEY)?|PASSWORD|PASSWD|"
    r"CREDENTIAL|AUTH(?:_TOKEN)?|PAT)(?:$|_)"
)
_SENSITIVE_HEADER_RE = re.compile(r"(?i)^(?:authorization|proxy-authorization|x-api-key|api-key)$")


class InventoryError(Exception):
    """Raised when an inventory input is invalid or unsafe."""


@dataclass(frozen=True)
class Consumer:
    credential: str
    client: str
    server: str
    config_path: str
    source: str
    restart: str


@dataclass(frozen=True)
class Unknown:
    client: str
    server: str
    config_path: str
    reason: str


@dataclass(frozen=True)
class InventoryReport:
    consumers: list[Consumer]
    unknown: list[Unknown]
    files_scanned: int
    mappings: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumers": [asdict(item) for item in self.consumers],
            "unknown": [asdict(item) for item in self.unknown],
            "summary": {
                "files_scanned": self.files_scanned,
                "mappings": self.mappings,
                "consumers": len(self.consumers),
                "unknown": len(self.unknown),
            },
            "notice": (
                "Read-only inventory. Credential values are never emitted or persisted; "
                "paths and names may themselves be sensitive."
            ),
        }


def _safe_relative(path: Path, root: Path) -> str:
    if path.is_symlink():
        raise InventoryError("config files must not be symbolic links")
    try:
        resolved = path.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
        if not resolved.is_relative_to(root_resolved):
            raise InventoryError("config file resolves outside config directory")
        return resolved.relative_to(root_resolved).as_posix()
    except InventoryError:
        raise
    except (OSError, ValueError) as exc:
        raise InventoryError("config file resolves outside config directory") from exc


def _read_text(path: Path, kind: str) -> str:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise InventoryError(f"cannot read {kind} file") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise InventoryError(f"{kind} file exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise InventoryError(f"cannot read {kind} file as UTF-8") from exc


def _load_mapping(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(_read_text(path, "mapping"))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise InventoryError("cannot read mapping file as JSON") from exc
    if not isinstance(raw, dict):
        raise InventoryError("mapping must be a JSON object of credential names to labels")

    mapping: dict[str, str] = {}
    for name, label in raw.items():
        if not isinstance(name, str) or not CREDENTIAL_NAME_RE.fullmatch(name):
            raise InventoryError("mapping names must be environment variable identifiers")
        if not isinstance(label, str) or not label.strip():
            raise InventoryError("mapping labels must be non-empty strings")
        label = label.strip()
        if len(label) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in label):
            raise InventoryError("mapping labels must be printable strings of at most 200 characters")
        if "|" in label or "/" in label or "\\" in label or label in {".", ".."}:
            raise InventoryError("mapping labels must not contain path separators or table delimiters")
        if name in mapping:
            raise InventoryError("duplicate mapping name")
        mapping[name] = label
    return mapping


def _reference_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _REFERENCE_RE.fullmatch(value.strip())
    if not match:
        return None
    return match.group("env") or match.group("scheme") or match.group("vault")


def _embedded_reference_names(value: str) -> list[str]:
    names: list[str] = []
    for match in _EMBEDDED_REFERENCE_RE.finditer(value):
        name = match.group("env") or match.group("scheme") or match.group("vault")
        if name and name not in names:
            names.append(name)
    return names


def _cell(value: str) -> str:
    return "".join(
        "?" if ord(char) < 32 or ord(char) == 127 else "\\|" if char == "|" else char
        for char in value
    )


def _server_entries(
    client: str, config_path: str, document: Any
) -> tuple[list[tuple[str, dict[str, Any]]], list[Unknown]]:
    unknown: list[Unknown] = []
    if client == "codex":
        servers = document.get("mcp_servers") if isinstance(document, dict) else None
        expected = "mcp_servers"
    else:
        servers = document.get("mcpServers") if isinstance(document, dict) else None
        expected = "mcpServers"

    if not isinstance(servers, dict):
        if isinstance(document, dict) and isinstance(document.get("projects"), dict):
            reason = f"missing top-level {expected}; project-scoped servers are unsupported"
            return [], [Unknown(client, "-", config_path, reason)]
        return [], []

    entries: list[tuple[str, dict[str, Any]]] = []
    projects = document.get("projects") if isinstance(document, dict) else None
    if client == "claude-code" and isinstance(projects, dict):
        if any(isinstance(item, dict) and item.get("mcpServers") for item in projects.values()):
            unknown.append(
                Unknown(client, "-", config_path, "project-scoped mcpServers are unsupported")
            )
    for name, config in servers.items():
        if not isinstance(name, str) or not isinstance(config, dict):
            unknown.append(Unknown(client, str(name), config_path, "server entry is not an object"))
            continue
        entries.append((name, config))
    return entries, unknown


def _add_consumer(
    consumers: list[Consumer],
    unknown: list[Unknown],
    *,
    client: str,
    server: str,
    config_path: str,
    source: str,
    raw_name: str,
    mapping: dict[str, str],
) -> None:
    if raw_name not in mapping:
        unknown.append(
            Unknown(client, server, config_path, f"credential {raw_name} not in mapping")
        )
        return
    consumers.append(
        Consumer(
            credential=mapping[raw_name],
            client=client,
            server=server,
            config_path=config_path,
            source=source,
            restart="unknown",
        )
    )


def _scan_args(
    consumers: list[Consumer],
    unknown: list[Unknown],
    args: Any,
    *,
    client: str,
    server: str,
    config_path: str,
    mapping: dict[str, str],
) -> None:
    if args is None:
        return
    if not isinstance(args, list):
        unknown.append(Unknown(client, server, config_path, "args is not a list"))
        return
    for index, arg in enumerate(args):
        if not isinstance(arg, str):
            unknown.append(Unknown(client, server, config_path, f"args[{index}] is not a string"))
            continue
        references = _embedded_reference_names(arg)
        for reference in references:
            _add_consumer(
                consumers,
                unknown,
                client=client,
                server=server,
                config_path=config_path,
                source=f"args[{index}]",
                raw_name=reference,
                mapping=mapping,
            )
        if not references and _SENSITIVE_ARG_RE.search(arg):
            unknown.append(
                Unknown(
                    client,
                    server,
                    config_path,
                    f"args[{index}] may contain a literal credential",
                )
            )


def _scan_env(
    consumers: list[Consumer],
    unknown: list[Unknown],
    env: Any,
    *,
    client: str,
    server: str,
    config_path: str,
    mapping: dict[str, str],
) -> None:
    if env is None:
        return
    if not isinstance(env, dict):
        unknown.append(Unknown(client, server, config_path, "env is not an object"))
        return
    for raw_name in sorted(env, key=str):
        source_name = str(raw_name)
        reference = _reference_name(env[raw_name])
        if reference is None:
            if _SENSITIVE_NAME_RE.search(source_name):
                unknown.append(
                    Unknown(
                        client,
                        server,
                        config_path,
                        f"literal env {source_name} has unknown credential source",
                    )
                )
            continue
        _add_consumer(
            consumers,
            unknown,
            client=client,
            server=server,
            config_path=config_path,
            source=f"env.{source_name}",
            raw_name=reference,
            mapping=mapping,
        )


def _scan_headers(
    consumers: list[Consumer],
    unknown: list[Unknown],
    headers: Any,
    *,
    client: str,
    server: str,
    config_path: str,
    mapping: dict[str, str],
    source_prefix: str = "headers",
) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        unknown.append(Unknown(client, server, config_path, "headers is not an object"))
        return
    for header in sorted(headers, key=str):
        header_name = str(header)
        reference = _reference_name(headers[header])
        if reference is None:
            if _SENSITIVE_HEADER_RE.fullmatch(header_name):
                unknown.append(
                    Unknown(
                        client,
                        server,
                        config_path,
                        f"literal header {header_name} has unknown credential source",
                    )
                )
            continue
        _add_consumer(
            consumers,
            unknown,
            client=client,
            server=server,
            config_path=config_path,
            source=f"{source_prefix}.{header_name}",
            raw_name=reference,
            mapping=mapping,
        )


def _scan_codex_server(
    name: str, config: dict[str, Any], config_path: str, mapping: dict[str, str]
) -> tuple[list[Consumer], list[Unknown]]:
    consumers: list[Consumer] = []
    unknown: list[Unknown] = []
    env_vars = config.get("env_vars", [])
    if env_vars is None:
        env_vars = []
    env_aliases: set[str] = set()
    if not isinstance(env_vars, list):
        unknown.append(Unknown("codex", name, config_path, "env_vars is not a list"))
    else:
        for index, item in enumerate(env_vars):
            raw_name: str | None = None
            if isinstance(item, str):
                raw_name = item
            elif isinstance(item, dict):
                source = item.get("source", "local")
                if set(item) <= {"name", "source"} and isinstance(item.get("name"), str) and source in {"local", "remote"}:
                    raw_name = item["name"]
                else:
                    unknown.append(
                        Unknown("codex", name, config_path, f"unsupported env_vars[{index}] entry")
                    )
            else:
                unknown.append(
                    Unknown("codex", name, config_path, f"unsupported env_vars[{index}] entry")
                )
            if raw_name is not None:
                env_aliases.add(raw_name)
                _add_consumer(
                    consumers,
                    unknown,
                    client="codex",
                    server=name,
                    config_path=config_path,
                    source="env_vars",
                    raw_name=raw_name,
                    mapping=mapping,
                )

    env_config = config.get("env")
    if isinstance(env_config, dict):
        env_config = {
            key: value for key, value in env_config.items() if str(key) not in env_aliases
        }
    _scan_env(consumers, unknown, env_config, client="codex", server=name, config_path=config_path, mapping=mapping)
    _scan_args(consumers, unknown, config.get("args"), client="codex", server=name, config_path=config_path, mapping=mapping)
    _scan_headers(
        consumers,
        unknown,
        config.get("http_headers"),
        client="codex",
        server=name,
        config_path=config_path,
        mapping=mapping,
        source_prefix="http_headers",
    )

    env_headers = config.get("env_http_headers")
    if env_headers is not None and not isinstance(env_headers, dict):
        unknown.append(Unknown("codex", name, config_path, "env_http_headers is not an object"))
    elif isinstance(env_headers, dict):
        for header in sorted(env_headers, key=str):
            raw_name = env_headers[header]
            if not isinstance(raw_name, str):
                unknown.append(Unknown("codex", name, config_path, f"env_http_headers.{header} is not a string"))
                continue
            _add_consumer(
                consumers,
                unknown,
                client="codex",
                server=name,
                config_path=config_path,
                source=f"env_http_headers.{header}",
                raw_name=raw_name,
                mapping=mapping,
            )

    bearer_name = config.get("bearer_token_env_var")
    if bearer_name is not None:
        if not isinstance(bearer_name, str):
            unknown.append(Unknown("codex", name, config_path, "bearer_token_env_var is not a string"))
        else:
            _add_consumer(
                consumers,
                unknown,
                client="codex",
                server=name,
                config_path=config_path,
                source="bearer_token_env_var",
                raw_name=bearer_name,
                mapping=mapping,
            )
    return consumers, unknown


def _scan_claude_server(
    name: str, config: dict[str, Any], config_path: str, mapping: dict[str, str]
) -> tuple[list[Consumer], list[Unknown]]:
    consumers: list[Consumer] = []
    unknown: list[Unknown] = []
    transport = config.get("type")
    if transport not in (None, "stdio", "http", "sse"):
        unknown.append(Unknown("claude-code", name, config_path, "unsupported transport type"))
    _scan_env(consumers, unknown, config.get("env"), client="claude-code", server=name, config_path=config_path, mapping=mapping)
    _scan_headers(consumers, unknown, config.get("headers"), client="claude-code", server=name, config_path=config_path, mapping=mapping)
    _scan_args(consumers, unknown, config.get("args"), client="claude-code", server=name, config_path=config_path, mapping=mapping)
    return consumers, unknown


def _load_document(path: Path) -> tuple[str, Any]:
    text = _read_text(path, "JSON config" if path.suffix == ".json" else "TOML config")
    if path.suffix == ".json":
        try:
            return "claude-code", json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise InventoryError("cannot parse JSON config as a supported Claude MCP config") from exc
    if path.suffix == ".toml":
        try:
            return "codex", tomllib.loads(text)
        except (tomllib.TOMLDecodeError, RecursionError) as exc:
            raise InventoryError("cannot parse TOML config as a supported Codex MCP config") from exc
    raise InventoryError("only explicit .json and .toml config files are supported")


def build_inventory(config_dir: Path, mapping_path: Path) -> InventoryReport:
    """Read explicit configs under ``config_dir`` without values or side effects."""
    source_root = config_dir.expanduser()
    if not source_root.is_dir():
        raise InventoryError("config path must be an existing directory")
    config_root = Path(os.path.realpath(source_root))
    mapping = _load_mapping(Path(os.path.realpath(mapping_path.expanduser())))

    consumers: list[Consumer] = []
    unknown: list[Unknown] = []
    try:
        candidates = sorted(path for path in config_root.iterdir() if path.is_file() or path.is_symlink())
    except OSError as exc:
        raise InventoryError("cannot list config directory") from exc
    try:
        mapping_resolved = Path(os.path.realpath(mapping_path.expanduser()))
    except OSError as exc:
        raise InventoryError("mapping file must exist") from exc
    try:
        config_resolved = config_root.resolve(strict=True)
    except OSError as exc:
        raise InventoryError("config path must be accessible") from exc
    filtered = []
    for path in candidates:
        try:
            if path.is_symlink():
                raise InventoryError("config files must not be symbolic links")
            resolved = path.resolve(strict=False)
            if resolved == mapping_resolved:
                continue
            if not resolved.is_relative_to(config_resolved):
                raise InventoryError("config file resolves outside config directory")
        except InventoryError:
            raise
        except OSError as exc:
            raise InventoryError("cannot resolve a config path") from exc
        filtered.append(path)
    candidates = filtered
    scanned = 0
    for path in candidates:
        relative = _safe_relative(path, config_root)
        if path.suffix in UNSUPPORTED_CONFIG_SUFFIXES:
            unknown.append(
                Unknown(
                    "unknown",
                    "-",
                    relative,
                    f"unsupported config format {path.suffix} (supported: .json, .toml)",
                )
            )
            continue
        if path.suffix not in SUPPORTED_SUFFIXES:
            continue
        scanned += 1
        client, document = _load_document(path)
        entries, entry_unknown = _server_entries(client, relative, document)
        unknown.extend(entry_unknown)
        for name, config in entries:
            if client == "codex":
                found, missing = _scan_codex_server(name, config, relative, mapping)
            else:
                found, missing = _scan_claude_server(name, config, relative, mapping)
            consumers.extend(found)
            unknown.extend(missing)

    consumers.sort(key=lambda item: (item.credential, item.client, item.server, item.source))
    unknown.sort(key=lambda item: (item.client, item.server, item.config_path, item.reason))
    return InventoryReport(
        consumers=consumers,
        unknown=unknown,
        files_scanned=scanned,
        mappings=len(mapping),
    )


def render_report(report: InventoryReport, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"

    lines = [
        "credential | client | server | config | source | restart",
        "---|---|---|---|---|---",
    ]
    for item in report.consumers:
        lines.append(
            f"{_cell(item.credential)} | {_cell(item.client)} | {_cell(item.server)} | "
            f"{_cell(item.config_path)} | {_cell(item.source)} | {_cell(item.restart)}"
        )
    if report.unknown:
        lines.extend(["", "unknown | client | server | config | reason", "---|---|---|---|---"])
        for item in report.unknown:
            lines.append(
                f"unknown | {_cell(item.client)} | {_cell(item.server)} | "
                f"{_cell(item.config_path)} | {_cell(item.reason)}"
            )
    lines.append("")
    lines.append(
        f"scanned {report.files_scanned} explicit file(s); "
        f"{len(report.consumers)} known consumer(s); "
        f"{len(report.unknown)} unknown item(s); mappings={report.mappings}"
    )
    lines.append(
        "Read-only: no values, vault, network, or subprocess access; "
        "paths and names may themselves be sensitive."
    )
    return "\n".join(lines) + "\n"
