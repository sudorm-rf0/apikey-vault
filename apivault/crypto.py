"""Cryptographic primitives for apikey-vault.

Design
------
- Key derivation: scrypt (memory-hard, OWASP-recommended parameters).
- Encryption: AES-256-GCM (authenticated encryption) via the ``cryptography``
  library, so ciphertexts are both confidential and tamper-evident.
- On-disk secret format: ``nonce(12B) || ciphertext || tag(16B)``.
- Master-password verification: we encrypt a fixed magic value at vault
  initialization; unlocking succeeds only if that magic decrypts correctly.
  The password itself is never stored.

The derived 32-byte key is the *only* thing that can decrypt the vault.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# scrypt parameters (OWASP recommended: N=2^17, r=8, p=1)
KDF_N = 2**17
KDF_R = 8
KDF_P = 1
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
TAG_BYTES = 16

# Fixed value used to verify the master password. Encrypting/decrypting this
# succeeds only with the correct derived key.
VERIFY_MAGIC = b"apikey-vault-verify-v1"

# scrypt params used to derive keys. Must not exceed OpenSSL limits.
assert KDF_N * KDF_R * 128 < 2**31, "scrypt parameters exceed OpenSSL limits"


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES key from the master password and salt."""
    if not isinstance(password, str):
        raise TypeError("password must be a str")
    if len(salt) != SALT_BYTES:
        raise ValueError(f"salt must be {SALT_BYTES} bytes")
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=KDF_N, r=KDF_R, p=KDF_P)
    return kdf.derive(password.encode("utf-8"))


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt bytes with AES-256-GCM. Returns nonce || ciphertext || tag."""
    if not isinstance(plaintext, bytes):
        raise TypeError("plaintext must be bytes")
    if len(key) != KEY_BYTES:
        raise ValueError(f"key must be {KEY_BYTES} bytes")
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt(payload: bytes, key: bytes) -> bytes:
    """Decrypt a payload produced by :func:`encrypt`. Raises on wrong key/tamper."""
    if len(key) != KEY_BYTES:
        raise ValueError(f"key must be {KEY_BYTES} bytes")
    if len(payload) < NONCE_BYTES + TAG_BYTES:
        raise ValueError("payload too short")
    nonce = payload[:NONCE_BYTES]
    ciphertext = payload[NONCE_BYTES:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def make_verify_blob(key: bytes) -> bytes:
    """Create the encrypted magic blob used to verify the master password."""
    return encrypt(VERIFY_MAGIC, key)


def check_verify_blob(blob: bytes, key: bytes) -> bool:
    """Return True iff ``blob`` decrypts to the expected magic with ``key``."""
    try:
        return decrypt(blob, key) == VERIFY_MAGIC
    except Exception:
        return False
