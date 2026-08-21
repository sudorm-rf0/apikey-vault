import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from apivault.server import VaultHTTPServer
from apivault.store import VaultStore


class APIClient:
    def __init__(self, base):
        self.base = base
        self.token = None

    def _request(self, method, path, body=None, token=True):
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw) if raw else None


@pytest.fixture()
def server(tmp_path):
    store = VaultStore(tmp_path)
    store.initialize("master-pw")
    httpd = VaultHTTPServer(("127.0.0.1", 0), store, ttl_seconds=3600)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, APIClient(f"http://127.0.0.1:{port}")
    httpd.shutdown()
    httpd.server_close()
    store.close()


def test_health(server):
    _, client = server
    status, body = client._request("GET", "/v1/health", token=False)
    assert status == 200
    assert body["initialized"] is True
    assert body["unlocked"] is False


def test_unlock_and_crud(server):
    _, client = server

    status, body = client._request("GET", "/v1/keys", token=False)
    assert status == 401

    status, body = client._request("POST", "/v1/unlock", body={"password": "wrong"}, token=False)
    assert status == 401

    status, body = client._request("POST", "/v1/unlock", body={"password": "master-pw"}, token=False)
    assert status == 200
    client.token = body["token"]

    status, body = client._request("GET", "/v1/keys")
    assert status == 200 and body["keys"] == []

    status, body = client._request("PUT", "/v1/keys/OPENAI_API_KEY",
                                   body={"value": "sk-abc", "description": "OpenAI"})
    assert status == 201

    status, body = client._request("GET", "/v1/keys/OPENAI_API_KEY")
    assert status == 200 and body["value"] == "sk-abc"

    status, body = client._request("GET", "/v1/keys")
    assert status == 200 and body["keys"][0]["name"] == "OPENAI_API_KEY"

    status, body = client._request("PUT", "/v1/keys/OPENAI_API_KEY", body={"value": "sk-new"})
    assert status == 200

    status, body = client._request("DELETE", "/v1/keys/OPENAI_API_KEY")
    assert status == 200

    status, body = client._request("GET", "/v1/keys/OPENAI_API_KEY")
    assert status == 404


def test_requires_token_when_locked(server):
    _, client = server
    status, body = client._request("GET", "/v1/keys", token=False)
    assert status == 401


def test_static_token(tmp_path):
    store = VaultStore(tmp_path)
    store.initialize("pw")
    store.unlock("pw")
    httpd = VaultHTTPServer(
        ("127.0.0.1", 0), store, static_tokens=["static-token-123"]
    )
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = APIClient(f"http://127.0.0.1:{port}")
        client.token = "static-token-123"
        status, body = client._request("PUT", "/v1/keys/K", body={"value": "v"})
        assert status == 201
        status, body = client._request("GET", "/v1/keys/K")
        assert body["value"] == "v"
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()


def test_unlock_rate_limit(server):
    _, client = server
    for _ in range(5):
        client._request("POST", "/v1/unlock", body={"password": "bad"}, token=False)
    status, body = client._request("POST", "/v1/unlock",
                                   body={"password": "master-pw"}, token=False)
    assert status == 429


def test_lock_invalidates_tokens(server):
    _, client = server
    status, body = client._request("POST", "/v1/unlock", body={"password": "master-pw"}, token=False)
    assert status == 200
    client.token = body["token"]
    assert client.token
    status, _ = client._request("POST", "/v1/lock", token=False)
    assert status == 200
    status, _ = client._request("GET", "/v1/keys")
    assert status == 401


def test_bad_body_returns_400(server):
    _, client = server
    status, body = client._request("POST", "/v1/unlock", body={"password": "master-pw"}, token=False)
    assert status == 200
    client.token = body["token"]
    status, _ = client._request("PUT", "/v1/keys/K", body={"notvalue": 1})
    assert status == 400
