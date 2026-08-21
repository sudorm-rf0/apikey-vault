"""SQLite-backed vault storage.

The vault database holds only ciphertext plus non-secret metadata; the only
secret in memory is the 32-byte derived key held while the vault is unlocked.
"""

from __future__ import annotations

import base64
import ctypes
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from apivault import crypto

SCHEMA_VERSION = 1

# Metadata keys stored in the `meta` table
META_SALT = "salt"
META_VERIFY = "verify"
META_VERSION = "version"
META_KDF_N = "kdf_n"
META_KDF_R = "kdf_r"
META_KDF_P = "kdf_p"
META_CREATED = "created_at"


class VaultError(Exception):
    """Base error for vault problems."""


class VaultNotInitializedError(VaultError):
    """Raised when the vault database does not exist / is not initialized."""


class VaultLockedError(VaultError):
    """Raised when an operation requires an unlocked vault."""


class VaultWrongPasswordError(VaultError):
    """Raised when the master password is incorrect."""


class KeyNotFoundError(VaultError):
    """Raised when a named key does not exist."""


class KeyExistsError(VaultError):
    """Raised when storing/renaming onto an existing name without overwrite."""


@dataclass(frozen=True)
class SecretMeta:
    """Non-secret metadata about a stored key."""

    name: str
    description: str | None
    created_at: str
    updated_at: str


def default_vault_dir() -> Path:
    """Return the default vault directory (~/.apikey-vault, overridable)."""
    env = os.environ.get("APIVAULT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".apikey-vault"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class VaultStore:
    """Encrypted vault backed by a single SQLite file.

    Thread-safety: uses a module-level lock around all DB operations so the
    HTTP server (threaded) can share one store safely.
    """

    def __init__(self, dir: Path | str | None = None):
        """Open (or lazily create) a vault inside ``dir``.

        ``dir`` defaults to ``$APIVAULT_DIR`` or ``~/.apikey-vault``; the
        database file is ``vault.db`` inside that directory.
        """
        self.dir = Path(dir).expanduser() if dir else default_vault_dir()
        self.path = self.dir / "vault.db"
        self._db: sqlite3.Connection | None = None
        self._key: bytes | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ paths
    @property
    def initialized(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    # ------------------------------------------------------------ low level
    def _connect(self) -> sqlite3.Connection:
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(
                str(self.path), check_same_thread=False
            )
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._create_schema()
        return self._db

    def _create_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS keys (
                name        TEXT PRIMARY KEY,
                description TEXT,
                payload     BLOB NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    def _meta_get(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def _meta_set(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ----------------------------------------------------------- initialize
    def initialize(self, password: str, description: str | None = None) -> None:
        """Create a brand-new vault. Fails if one already exists."""
        with self._lock:
            if self.initialized:
                raise VaultError(f"vault already exists at {self.path}")
            salt = os.urandom(crypto.SALT_BYTES)
            key = crypto.derive_key(password, salt)
            try:
                db = self._connect()
                db.execute("BEGIN IMMEDIATE")
                try:
                    self._meta_set(META_SALT, base64.b64encode(salt).decode())
                    self._meta_set(
                        META_VERIFY,
                        base64.b64encode(crypto.make_verify_blob(key)).decode(),
                    )
                    self._meta_set(META_VERSION, str(SCHEMA_VERSION))
                    self._meta_set(META_KDF_N, str(crypto.KDF_N))
                    self._meta_set(META_KDF_R, str(crypto.KDF_R))
                    self._meta_set(META_KDF_P, str(crypto.KDF_P))
                    self._meta_set(META_CREATED, _now())
                    if description:
                        self._meta_set("description", description)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            finally:
                _wipe(key)
            self._chmod_private()

    def _chmod_private(self) -> None:
        try:
            os.chmod(self.path, 0o600)
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass  # Windows or exotic FS: best effort

    # -------------------------------------------------------------- unlock
    def verify_password(self, password: str) -> bool:
        """Return True iff ``password`` is the correct master password.

        Works whether or not the vault is currently unlocked (does not change
        the unlocked state). Used by the HTTP server so /v1/unlock can mint a
        token even when the vault was already unlocked at startup.
        """
        with self._lock:
            if not self.initialized:
                return False
            db = self._connect()
            salt_b64 = self._meta_get(META_SALT)
            verify_b64 = self._meta_get(META_VERIFY)
            if not salt_b64 or not verify_b64:
                return False
            salt = base64.b64decode(salt_b64)
            verify_blob = base64.b64decode(verify_b64)
            key = crypto.derive_key(password, salt)
            try:
                return crypto.check_verify_blob(verify_blob, key)
            finally:
                _wipe(key)

    def unlock(self, password: str) -> None:
        """Derive the key and verify the password. Raises on failure."""
        with self._lock:
            if not self.initialized:
                raise VaultNotInitializedError(
                    f"vault not initialized at {self.path}; run `apivault init`"
                )
            if self.unlocked:
                if not self.verify_password(password):
                    raise VaultWrongPasswordError("wrong master password")
                return
            db = self._connect()
            salt_b64 = self._meta_get(META_SALT)
            verify_b64 = self._meta_get(META_VERIFY)
            if not salt_b64 or not verify_b64:
                raise VaultError("vault metadata is corrupt (missing salt/verify)")
            salt = base64.b64decode(salt_b64)
            verify_blob = base64.b64decode(verify_b64)
            key = crypto.derive_key(password, salt)
            if not crypto.check_verify_blob(verify_blob, key):
                _wipe(key)
                raise VaultWrongPasswordError("wrong master password")
            self._key = key

    def lock(self) -> None:
        """Wipe the in-memory key and lock the vault."""
        with self._lock:
            if self._key is not None:
                _wipe(self._key)
                self._key = None

    def _require_key(self) -> bytes:
        if not self.unlocked:
            raise VaultLockedError("vault is locked; unlock with a password first")
        return self._key  # type: ignore[return-value]

    # ----------------------------------------------------------------- CRUD
    def set(
        self,
        name: str,
        value: str,
        description: str | None = None,
        overwrite: bool = True,
    ) -> None:
        """Encrypt and store a secret under ``name``."""
        if not name or "\x00" in name or "/" in name or "\\" in name:
            raise ValueError("name must be non-empty and contain no path separators")
        with self._lock:
            key = self._require_key()
            exists = self._row(name) is not None
            if exists and not overwrite:
                raise KeyExistsError(f"key {name!r} already exists")
            payload = crypto.encrypt(value.encode("utf-8"), key)
            now = _now()
            db = self._connect()
            if exists:
                db.execute(
                    "UPDATE keys SET payload = ?, description = ?, updated_at = ? "
                    "WHERE name = ?",
                    (payload, description, now, name),
                )
            else:
                db.execute(
                    "INSERT INTO keys (name, description, payload, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, description, payload, now, now),
                )
            db.commit()

    def _row(self, name: str) -> tuple | None:
        return self._db.execute(
            "SELECT name, description, payload, created_at, updated_at "
            "FROM keys WHERE name = ?",
            (name,),
        ).fetchone()

    def get(self, name: str) -> str:
        """Return the decrypted value for ``name``."""
        with self._lock:
            key = self._require_key()
            row = self._row(name)
            if row is None:
                raise KeyNotFoundError(f"key {name!r} not found")
            plaintext = crypto.decrypt(row[2], key)
            try:
                return plaintext.decode("utf-8")
            finally:
                _wipe(plaintext)

    def metadata(self, name: str) -> SecretMeta:
        with self._lock:
            self._require_key()
            row = self._row(name)
            if row is None:
                raise KeyNotFoundError(f"key {name!r} not found")
            return SecretMeta(
                name=row[0],
                description=row[1],
                created_at=row[3],
                updated_at=row[4],
            )

    def list(self) -> list[SecretMeta]:
        """List metadata for all keys (never values)."""
        with self._lock:
            self._require_key()
            rows = self._db.execute(
                "SELECT name, description, created_at, updated_at "
                "FROM keys ORDER BY name"
            ).fetchall()
            return [
                SecretMeta(name=r[0], description=r[1], created_at=r[2], updated_at=r[3])
                for r in rows
            ]

    def delete(self, name: str) -> None:
        with self._lock:
            self._require_key()
            db = self._connect()
            cur = db.execute("DELETE FROM keys WHERE name = ?", (name,))
            if cur.rowcount == 0:
                raise KeyNotFoundError(f"key {name!r} not found")
            db.commit()

    def rename(self, old: str, new: str) -> None:
        if not new or "\x00" in new or "/" in new or "\\" in new:
            raise ValueError("new name must be non-empty and contain no path separators")
        with self._lock:
            self._require_key()
            db = self._connect()
            if self._row(new) is not None:
                raise KeyExistsError(f"key {new!r} already exists")
            cur = db.execute(
                "UPDATE keys SET name = ?, updated_at = ? WHERE name = ?",
                (new, _now(), old),
            )
            if cur.rowcount == 0:
                raise KeyNotFoundError(f"key {old!r} not found")
            db.commit()

    # ------------------------------------------------------ password change
    def change_password(self, new_password: str) -> None:
        """Re-encrypt every secret and the verify blob with a new password."""
        with self._lock:
            old_key = self._require_key()
            salt = os.urandom(crypto.SALT_BYTES)
            new_key = crypto.derive_key(new_password, salt)
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute(
                    "SELECT name, payload FROM keys"
                ).fetchall()
                for name, payload in rows:
                    plaintext = crypto.decrypt(payload, old_key)
                    try:
                        new_payload = crypto.encrypt(plaintext, new_key)
                    finally:
                        _wipe(plaintext)
                    db.execute(
                        "UPDATE keys SET payload = ? WHERE name = ?",
                        (new_payload, name),
                    )
                self._meta_set(META_SALT, base64.b64encode(salt).decode())
                self._meta_set(
                    META_VERIFY,
                    base64.b64encode(crypto.make_verify_blob(new_key)).decode(),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                _wipe(new_key)
            # swap in-memory key to the new one so the session stays usable
            if self._key is not None:
                _wipe(self._key)
            self._key = new_key

    # ------------------------------------------------------- export/import
    def export_bytes(self) -> bytes:
        """Return the raw encrypted database file.

        Safe to move between devices: every secret is AES-256-GCM ciphertext
        and the file can only be unlocked with the master password. Requires an
        unlocked vault so WAL is fully checkpointed into the main file.
        """
        with self._lock:
            self._require_key()
            db = self._connect()
            db.execute("PRAGMA wal_checkpoint(FULL)")
            db.commit()
            return self.path.read_bytes()

    def import_bytes(self, data: bytes) -> None:
        """Atomically replace the vault with another encrypted database.

        The uploaded bytes are validated (must be a SQLite vault containing a
        salt and verify blob) before anything is touched. The vault is left
        locked afterwards because the in-memory key no longer matches.
        """
        if not data:
            raise VaultError("import data is empty")
        if len(data) > 64 * 1024 * 1024:
            raise VaultError("import data too large (limit 64 MiB)")
        with self._lock:
            # Validate the candidate file in a temp location first.
            self.dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix="apivault-import-", suffix=".db", dir=str(self.dir)
            )
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                self._validate_db_file(tmp_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            # Commit and close the live connection, then swap files.
            if self._db is not None:
                self._db.execute("PRAGMA wal_checkpoint(FULL)")
                self._db.commit()
                self._db.close()
                self._db = None
            if self._key is not None:
                _wipe(self._key)
                self._key = None

            shutil.move(tmp_path, self.path)
            for suffix in ("-wal", "-shm"):
                try:
                    os.unlink(str(self.path) + suffix)
                except OSError:
                    pass
            self._chmod_private()

    @staticmethod
    def _validate_db_file(path: str) -> None:
        """Raise VaultError unless ``path`` looks like a valid vault database."""
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise VaultError(f"imported file is not a valid vault: {exc}") from exc
        try:
            rows = con.execute(
                "SELECT key FROM meta WHERE key IN ('salt', 'verify')"
            ).fetchall()
            tables = [
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        except sqlite3.Error as exc:
            raise VaultError(f"imported file is not a valid vault: {exc}") from exc
        finally:
            con.close()
        if len(rows) != 2 or "keys" not in tables or "meta" not in tables:
            raise VaultError("imported file is not a valid apikey-vault database")

    def close(self) -> None:
        with self._lock:
            self.lock()
            if self._db is not None:
                self._db.close()
                self._db = None


def _wipe(data: bytes) -> None:
    """Best-effort zeroization of sensitive bytes in memory."""
    try:
        buf = (ctypes.c_char * len(data)).from_buffer(data)
        ctypes.memset(buf, 0, len(data))
    except Exception:
        pass
