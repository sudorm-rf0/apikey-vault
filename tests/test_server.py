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


# ---------------------------------------------------------------------------
# GUI static serving + new endpoints
# ---------------------------------------------------------------------------

def test_gui_static_files(server):
    httpd, _ = server
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    with urllib.request.urlopen(base + "/", timeout=10) as resp:
        html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "text/html" in resp.headers["Content-Type"]
        assert "apikey-vault" in html

    with urllib.request.urlopen(base + "/app/style.css", timeout=10) as resp:
        assert resp.status == 200
        assert "text/css" in resp.headers["Content-Type"]
        assert "Content-Security-Policy" in resp.headers
        assert "Cache-Control" in resp.headers


def test_gui_path_traversal_blocked(server):
    httpd, client = server
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    req = urllib.request.Request(base + "/app/../../apivault/server.py")
    try:
        urllib.request.urlopen(req, timeout=10)
        assert False, "traversal should be blocked"
    except urllib.error.HTTPError as exc:
        assert exc.code in (400, 404)


def test_export_returns_encrypted_db(server):
    _, client = server
    client._request("POST", "/v1/unlock", body={"password": "master-pw"}, token=False)
    client.token = client.token or _unlock_token(client)
    req = urllib.request.Request(
        client.base + "/v1/export",
        headers={"Authorization": f"Bearer {client.token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "application/octet-stream"
        assert data[:16] == b"SQLite format 3\x00"
        assert b"master-pw" not in data
        assert b"sk-" not in data


def _unlock_token(client):
    import urllib.request as _ur

    body = json.dumps({"password": "master-pw"}).encode()
    req = _ur.Request(client.base + "/v1/unlock", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with _ur.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["token"]


def test_change_password_endpoint(server):
    _, client = server
    status, body = client._request("POST", "/v1/unlock", body={"password": "master-pw"}, token=False)
    client.token = body["token"]

    # wrong old password -> 401
    status, body = client._request("POST", "/v1/password",
                                   body={"old_password": "nope", "new_password": "newpw"})
    assert status == 401

    # correct -> 200
    status, body = client._request("POST", "/v1/password",
                                   body={"old_password": "master-pw", "new_password": "newpw"})
    assert status == 200

    # old no longer works, new works
    client.token = None
    status, _ = client._request("POST", "/v1/unlock", body={"password": "master-pw"}, token=False)
    assert status == 401
    status, body = client._request("POST", "/v1/unlock", body={"password": "newpw"}, token=False)
    assert status == 200


def test_import_replaces_vault(tmp_path):
    # vault A: one key
    store_a = VaultStore(tmp_path / "a")
    store_a.initialize("pw-a")
    store_a.unlock("pw-a")
    store_a.set("KEY_A", "value-a")
    blob_a = store_a.export_bytes()
    store_a.close()

    # vault B server: another key
    store_b = VaultStore(tmp_path / "b")
    store_b.initialize("pw-b")
    httpd = VaultHTTPServer(("127.0.0.1", 0), store_b)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = APIClient(f"http://127.0.0.1:{port}")
        status, body = client._request("POST", "/v1/unlock", body={"password": "pw-b"}, token=False)
        client.token = body["token"]
        client._request("PUT", "/v1/keys/KEY_B", body={"value": "value-b"})

        # import A's encrypted db over B
        import urllib.request as _ur

        req = _ur.Request(
            client.base + "/v1/import",
            data=blob_a,
            headers={"Authorization": f"Bearer {client.token}", "Content-Type": "application/octet-stream"},
            method="POST",
        )
        with _ur.urlopen(req, timeout=10) as resp:
            assert resp.status == 200

        # tokens were revoked by import, so the client is unauthenticated now
        status, _ = client._request("GET", "/v1/keys")
        assert status == 401
        status, body = client._request("POST", "/v1/unlock", body={"password": "pw-a"}, token=False)
        assert status == 200
        client.token = body["token"]
        status, body = client._request("GET", "/v1/keys")
        assert status == 200
        names = [k["name"] for k in body["keys"]]
        assert "KEY_A" in names and "KEY_B" not in names
    finally:
        httpd.shutdown()
        httpd.server_close()
        store_b.close()


def test_static_token_survives_lock(tmp_path):
    store = VaultStore(tmp_path)
    store.initialize("pw")
    store.unlock("pw")
    httpd = VaultHTTPServer(("127.0.0.1", 0), store, static_tokens=["static-x"])
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = APIClient(f"http://127.0.0.1:{port}")
        client.token = "static-x"
        status, _ = client._request("GET", "/v1/keys")
        assert status == 200
        client._request("POST", "/v1/lock", token=False)
        # token survives, vault locked -> 423 not 401
        status, _ = client._request("GET", "/v1/keys")
        assert status == 423
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()


def test_init_endpoint(tmp_path):
    store = VaultStore(tmp_path / "fresh")
    httpd = VaultHTTPServer(("127.0.0.1", 0), store)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = APIClient(f"http://127.0.0.1:{port}")
        status, body = client._request("GET", "/v1/health", token=False)
        assert status == 200 and body["initialized"] is False

        status, body = client._request("POST", "/v1/init",
                                       body={"password": "new-pw"}, token=False)
        assert status == 201

        status, _ = client._request("POST", "/v1/init",
                                    body={"password": "x"}, token=False)
        assert status == 409

        status, body = client._request("POST", "/v1/unlock",
                                       body={"password": "new-pw"}, token=False)
        assert status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()
