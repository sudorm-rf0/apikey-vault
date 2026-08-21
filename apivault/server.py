"""Local HTTP API so AI agents (Codex / Claude) can use the vault.

Design
------
- ``ThreadingHTTPServer`` bound to 127.0.0.1 by default (``--host`` overrides).
- Bearer-token auth. Tokens are random 32-byte URL-safe strings; only their
  SHA-256 digests are kept in memory. Dynamic tokens expire after ``ttl``;
  static tokens passed via ``--token`` never expire.
- The vault may start locked and be unlocked via ``POST /v1/unlock`` (which
  requires the master password), or the server may start already unlocked when
  a password is available at startup.
- ``/v1/unlock`` is rate-limited per IP to slow brute force.
- Every response carries ``Cache-Control: no-store``.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from apivault.store import (
    KeyNotFoundError,
    VaultLockedError,
    VaultNotInitializedError,
    VaultStore,
    VaultWrongPasswordError,
)

MAX_BODY_BYTES = 1024 * 1024  # 1 MiB
DEFAULT_TTL_SECONDS = 12 * 3600
UNLOCK_MAX_FAILURES = 5
UNLOCK_COOLDOWN_SECONDS = 60


class TokenStore:
    """In-memory bearer tokens. Only SHA-256 digests are stored."""

    def __init__(self, static_tokens: list[str] | None = None):
        self._tokens: dict[str, float | None] = {}  # digest -> expiry (None = static)
        for token in static_tokens or []:
            self._tokens[_digest(token)] = None

    def issue(self, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[_digest(token)] = time.time() + ttl_seconds
        return token

    def verify(self, token: str) -> bool:
        d = _digest(token)
        exp = self._tokens.get(d)
        if exp is None:
            return d in self._tokens
        if exp < time.time():
            self._tokens.pop(d, None)
            return False
        return True

    def revoke(self, token: str) -> None:
        self._tokens.pop(_digest(token), None)

    def revoke_all(self) -> None:
        self._tokens.clear()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class VaultHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        addr: tuple[str, int],
        store: VaultStore,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        static_tokens: list[str] | None = None,
    ):
        self.vault = store
        self.tokens = TokenStore(static_tokens)
        self.ttl_seconds = ttl_seconds
        self._failures: dict[str, tuple[int, float]] = {}  # ip -> (count, window_start)
        super().__init__(addr, _Handler)

    # ------------------------------------------------------------- rate limit
    def unlock_allowed(self, ip: str) -> bool:
        count, window = self._failures.get(ip, (0, 0.0))
        if count >= UNLOCK_MAX_FAILURES and time.time() - window < UNLOCK_COOLDOWN_SECONDS:
            return False
        return True

    def record_failure(self, ip: str) -> None:
        count, window = self._failures.get(ip, (0, 0.0))
        if time.time() - window >= UNLOCK_COOLDOWN_SECONDS:
            count, window = 0, time.time()
        self._failures[ip] = (count + 1, window)

    def reset_failures(self, ip: str) -> None:
        self._failures.pop(ip, None)


class _Handler(BaseHTTPRequestHandler):
    server: VaultHTTPServer  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    # silence default stderr logging of every request
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    # --------------------------------------------------------------- helpers
    def _send(
        self, code: int, payload: dict | list | None, headers: dict | None = None
    ) -> None:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _error(self, code: int, message: str, headers: dict | None = None) -> None:
        self._send(code, {"error": message}, headers=headers)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("invalid or oversized request body")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _client_ip(self) -> str:
        return self.client_address[0]

    def _require_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[len("Bearer "):].strip()
            if token and self.server.tokens.verify(token):
                return token
        self._error(401, "unauthorized: provide a valid bearer token")
        return None

    # ---------------------------------------------------------------- routes
    def _route(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
        method = self.command
        ip = self._client_ip()

        if parts == ["v1", "health"] and method == "GET":
            self._health()
        elif parts == ["v1", "unlock"] and method == "POST":
            self._unlock(ip)
        elif parts == ["v1", "lock"] and method == "POST":
            self._lock()
        elif parts == ["v1", "keys"] and method == "GET":
            token = self._require_token()
            if token is not None:
                self._list_keys()
        elif len(parts) == 3 and parts[:2] == ["v1", "keys"] and method == "PUT":
            token = self._require_token()
            if token is not None:
                self._put_key(parts[2])
        elif len(parts) == 3 and parts[:2] == ["v1", "keys"] and method == "GET":
            token = self._require_token()
            if token is not None:
                self._get_key(parts[2])
        elif len(parts) == 3 and parts[:2] == ["v1", "keys"] and method == "DELETE":
            token = self._require_token()
            if token is not None:
                self._delete_key(parts[2])
        else:
            self._error(404, "not found")

    def _health(self) -> None:
        self._send(200, {
            "status": "ok",
            "initialized": self.server.vault.initialized,
            "unlocked": self.server.vault.unlocked,
            "api": "v1",
        })

    def _unlock(self, ip: str) -> None:
        if not self.server.unlock_allowed(ip):
            self._error(
                429,
                "too many failed unlock attempts; try again later",
                headers={"Retry-After": str(UNLOCK_COOLDOWN_SECONDS)},
            )
            return
        try:
            data = self._read_json()
            password = data.get("password")
        except Exception:
            self._error(400, "invalid request body")
            return
        if not isinstance(password, str) or not password:
            self._error(400, "password is required")
            return
        try:
            self.server.vault.unlock(password)
        except VaultNotInitializedError:
            self._error(500, "vault is not initialized")
            return
        except VaultWrongPasswordError:
            self.server.record_failure(ip)
            self._error(401, "invalid password")
            return
        self.server.reset_failures(ip)
        token = self.server.tokens.issue(self.server.ttl_seconds)
        self._send(200, {
            "token": token,
            "ttl_seconds": self.server.ttl_seconds,
            "expires_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() + self.server.ttl_seconds),
            ),
        })

    def _lock(self) -> None:
        # no auth required: locking is a security-positive action
        self.server.tokens.revoke_all()
        self.server.vault.lock()
        self._send(200, {"status": "locked"})

    def _check_unlocked(self) -> bool:
        if not self.server.vault.initialized:
            self._error(500, "vault is not initialized")
            return False
        if not self.server.vault.unlocked:
            self._error(423, "vault is locked; POST /v1/unlock first")
            return False
        return True

    def _list_keys(self) -> None:
        if not self._check_unlocked():
            return
        metas = self.server.vault.list()
        self._send(200, {"keys": [
            {
                "name": m.name,
                "description": m.description,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            }
            for m in metas
        ]})

    def _put_key(self, name: str) -> None:
        if not self._check_unlocked():
            return
        try:
            data = self._read_json()
        except Exception:
            self._error(400, "invalid request body")
            return
        value = data.get("value")
        if not isinstance(value, str):
            self._error(400, "field 'value' (string) is required")
            return
        description = data.get("description")
        if description is not None and not isinstance(description, str):
            self._error(400, "field 'description' must be a string")
            return
        try:
            existed = self.server.vault.metadata(name)  # may raise KeyNotFoundError
        except KeyNotFoundError:
            existed = None
        try:
            self.server.vault.set(name, value, description)
        except ValueError as exc:
            self._error(400, str(exc))
            return
        self._send(201 if existed is None else 200, {
            "name": name,
            "status": "created" if existed is None else "updated",
        })

    def _get_key(self, name: str) -> None:
        if not self._check_unlocked():
            return
        try:
            value = self.server.vault.get(name)
        except KeyNotFoundError:
            self._error(404, f"key {name!r} not found")
            return
        self._send(200, {"name": name, "value": value})

    def _delete_key(self, name: str) -> None:
        if not self._check_unlocked():
            return
        try:
            self.server.vault.delete(name)
        except KeyNotFoundError:
            self._error(404, f"key {name!r} not found")
            return
        self._send(200, {"status": "deleted", "name": name})

    # ---------------------------------------------------------------- entry
    def do_GET(self) -> None:  # noqa: N802
        self._route()

    def do_PUT(self) -> None:  # noqa: N802
        self._route()

    def do_POST(self) -> None:  # noqa: N802
        self._route()

    def do_DELETE(self) -> None:  # noqa: N802
        self._route()


def serve(
    store: VaultStore,
    *,
    host: str = "127.0.0.1",
    port: int = 8417,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    static_tokens: list[str] | None = None,
) -> None:
    """Run the HTTP server until KeyboardInterrupt."""
    httpd = VaultHTTPServer(
        (host, port), store, ttl_seconds=ttl_seconds, static_tokens=static_tokens
    )
    print(f"apikey-vault API listening on http://{host}:{port}  (vault: {store.path})")
    print(f"health: GET /v1/health | unlock: POST /v1/unlock")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        store.close()
