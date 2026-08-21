import pytest

from apivault.store import (
    KeyNotFoundError,
    VaultLockedError,
    VaultNotInitializedError,
    VaultStore,
    VaultWrongPasswordError,
)


@pytest.fixture()
def store(tmp_path):
    s = VaultStore(tmp_path)
    s.initialize("master-pw")
    s.unlock("master-pw")
    yield s
    s.close()


def test_not_initialized(tmp_path):
    s = VaultStore(tmp_path / "empty")
    with pytest.raises(VaultNotInitializedError):
        s.unlock("pw")
    s.close()


def test_wrong_password(tmp_path):
    s = VaultStore(tmp_path)
    s.initialize("right")
    with pytest.raises(VaultWrongPasswordError):
        s.unlock("wrong")
    assert not s.unlocked
    s.close()


def test_locked_operations(tmp_path):
    s = VaultStore(tmp_path)
    s.initialize("pw")
    with pytest.raises(VaultLockedError):
        s.set("K", "v")
    with pytest.raises(VaultLockedError):
        s.get("K")
    s.close()


def test_crud(store):
    store.set("OPENAI_API_KEY", "sk-abc", "OpenAI key")
    assert store.get("OPENAI_API_KEY") == "sk-abc"
    meta = store.metadata("OPENAI_API_KEY")
    assert meta.description == "OpenAI key"
    assert meta.created_at == meta.updated_at

    # overwrite updates the value and timestamp
    store.set("OPENAI_API_KEY", "sk-new", "rotated")
    assert store.get("OPENAI_API_KEY") == "sk-new"

    names = [m.name for m in store.list()]
    assert names == ["OPENAI_API_KEY"]

    store.rename("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    with pytest.raises(KeyNotFoundError):
        store.get("OPENAI_API_KEY")
    assert store.get("ANTHROPIC_API_KEY") == "sk-new"

    store.delete("ANTHROPIC_API_KEY")
    assert store.list() == []
    with pytest.raises(KeyNotFoundError):
        store.get("ANTHROPIC_API_KEY")


def test_unicode_values(store):
    store.set("MULTI", "密钥值 with 中文 & emoji 🚀")
    assert store.get("MULTI") == "密钥值 with 中文 & emoji 🚀"


def test_bad_names_rejected(store):
    with pytest.raises(ValueError):
        store.set("has/slash", "v")
    with pytest.raises(ValueError):
        store.rename("MULTI", "bad\\name")


def test_no_plaintext_on_disk(tmp_path):
    s = VaultStore(tmp_path)
    s.initialize("pw")
    s.unlock("pw")
    s.set("SECRET", "super-secret-plaintext-marker-xyz")
    s.close()
    raw = (tmp_path / "vault.db").read_bytes()
    assert b"super-secret-plaintext-marker-xyz" not in raw


def test_change_password(tmp_path):
    s = VaultStore(tmp_path)
    s.initialize("old-pw")
    s.unlock("old-pw")
    s.set("K", "v1")
    s.change_password("new-pw")
    s.lock()
    with pytest.raises(VaultWrongPasswordError):
        s.unlock("old-pw")
    s.unlock("new-pw")
    assert s.get("K") == "v1"
    s.close()


def test_verify_password(store):
    assert store.verify_password("master-pw") is True
    assert store.verify_password("nope") is False
    # still works while unlocked
    assert store.unlocked
    assert store.verify_password("master-pw") is True


def test_import_creates_backup(tmp_path):
    s = VaultStore(tmp_path)
    s.initialize("pw")
    s.unlock("pw")
    s.set("PRECIOUS", "value-1")
    s.close()

    # build a second vault to import
    other = VaultStore(tmp_path / "other")
    other.initialize("pw2")
    other.unlock("pw2")
    other.set("NEW", "value-2")
    blob = other.export_bytes()
    other.close()

    s2 = VaultStore(tmp_path)
    s2.import_bytes(blob)
    backups = list(tmp_path.glob("vault.db.backup-*"))
    assert len(backups) == 1
    # the backup is the OLD vault (encrypted, valid sqlite)
    raw = backups[0].read_bytes()
    assert raw[:16] == b"SQLite format 3\x00"
    assert b"value-1" not in raw

    # the imported vault works
    s2.unlock("pw2")
    assert s2.get("NEW") == "value-2"
    s2.close()


def test_import_with_spaces_in_path(tmp_path):
    weird = tmp_path / "vault with spaces"
    s = VaultStore(weird)
    s.initialize("pw")
    s.unlock("pw")
    s.set("K", "v")
    blob = s.export_bytes()
    s.close()

    target = tmp_path / "another dir with spaces"
    t = VaultStore(target)
    t.initialize("pwA")
    t.unlock("pwA")
    t.set("OLD", "x")
    t.close()

    t2 = VaultStore(target)
    t2.import_bytes(blob)  # should not raise despite spaces in path
    t2.unlock("pw")
    assert t2.get("K") == "v"
    t2.close()
