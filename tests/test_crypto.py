import pytest

from apivault import crypto


def test_encrypt_decrypt_roundtrip():
    key = crypto.derive_key("correct horse battery staple", b"\x01" * 16)
    payload = crypto.encrypt(b"sk-secret-value", key)
    assert crypto.decrypt(payload, key) == b"sk-secret-value"


def test_same_plaintext_produces_different_ciphertexts():
    key = crypto.derive_key("pw", b"\x02" * 16)
    a = crypto.encrypt(b"same", key)
    b = crypto.encrypt(b"same", key)
    assert a != b


def test_wrong_key_fails():
    key1 = crypto.derive_key("pw-one", b"\x03" * 16)
    key2 = crypto.derive_key("pw-two", b"\x03" * 16)
    payload = crypto.encrypt(b"top-secret", key1)
    with pytest.raises(Exception):
        crypto.decrypt(payload, key2)


def test_tampered_payload_fails():
    key = crypto.derive_key("pw", b"\x04" * 16)
    payload = bytearray(crypto.encrypt(b"top-secret", key))
    payload[-1] ^= 0xFF  # flip a bit in the tag/ciphertext
    with pytest.raises(Exception):
        crypto.decrypt(bytes(payload), key)


def test_short_payload_rejected():
    key = crypto.derive_key("pw", b"\x05" * 16)
    with pytest.raises(ValueError):
        crypto.decrypt(b"too-short", key)


def test_verify_blob():
    key = crypto.derive_key("pw", b"\x06" * 16)
    blob = crypto.make_verify_blob(key)
    assert crypto.check_verify_blob(blob, key) is True
    wrong = crypto.derive_key("nope", b"\x06" * 16)
    assert crypto.check_verify_blob(blob, wrong) is False
    assert crypto.check_verify_blob(b"garbage", key) is False
