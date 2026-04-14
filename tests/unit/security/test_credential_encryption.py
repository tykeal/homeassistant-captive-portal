# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Fernet credential encryption module."""

from __future__ import annotations

import os
import stat

import pytest
from cryptography.fernet import InvalidToken

from captive_portal.security.credential_encryption import (
    _load_or_create_key,
    decrypt_credential,
    encrypt_credential,
)


@pytest.fixture
def key_path(tmp_path: object) -> str:
    """Return a temporary key file path that does not yet exist.

    Args:
        tmp_path: Pytest tmp_path fixture.

    Returns:
        Path string for a temporary key file.
    """
    return os.path.join(str(tmp_path), "test.key")


class TestLoadOrCreateKey:
    """Tests for _load_or_create_key()."""

    def test_auto_generates_key_file(self, key_path: str) -> None:
        """Key file is created when it does not exist."""
        assert not os.path.exists(key_path)
        key = _load_or_create_key(key_path)
        assert os.path.exists(key_path)
        assert len(key) == 44  # Fernet key is 44 bytes base64

    def test_key_file_permissions(self, key_path: str) -> None:
        """Key file has 0o600 permissions (owner read/write only)."""
        _load_or_create_key(key_path)
        mode = os.stat(key_path).st_mode
        assert mode & 0o777 == stat.S_IRUSR | stat.S_IWUSR  # 0o600

    def test_reuses_existing_key(self, key_path: str) -> None:
        """Same key is returned across multiple calls."""
        key1 = _load_or_create_key(key_path)
        key2 = _load_or_create_key(key_path)
        assert key1 == key2

    def test_creates_parent_directory(self, tmp_path: object) -> None:
        """Parent directory is created if it does not exist."""
        nested_path = os.path.join(str(tmp_path), "subdir", "deep", "test.key")
        key = _load_or_create_key(nested_path)
        assert os.path.exists(nested_path)
        assert len(key) == 44


class TestEncryptCredential:
    """Tests for encrypt_credential()."""

    def test_encrypt_returns_nonempty_string(self, key_path: str) -> None:
        """Encryption returns a non-empty ciphertext string."""
        ct = encrypt_credential("my_secret", key_path=key_path)
        assert isinstance(ct, str)
        assert len(ct) > 0
        assert ct != "my_secret"

    def test_encrypt_empty_raises_value_error(self, key_path: str) -> None:
        """Empty plaintext raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            encrypt_credential("", key_path=key_path)

    def test_encrypt_different_calls_produce_different_ciphertext(self, key_path: str) -> None:
        """Two encryptions of the same plaintext produce different ciphertexts (due to IV)."""
        ct1 = encrypt_credential("same_secret", key_path=key_path)
        ct2 = encrypt_credential("same_secret", key_path=key_path)
        # Fernet uses unique IV each time
        assert ct1 != ct2


class TestDecryptCredential:
    """Tests for decrypt_credential()."""

    def test_decrypt_empty_raises_value_error(self, key_path: str) -> None:
        """Empty ciphertext raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            decrypt_credential("", key_path=key_path)

    def test_decrypt_invalid_ciphertext_raises(self, key_path: str) -> None:
        """Invalid ciphertext raises InvalidToken."""
        # Ensure a key exists first
        _load_or_create_key(key_path)
        with pytest.raises(InvalidToken):
            decrypt_credential("not-valid-ciphertext", key_path=key_path)

    def test_decrypt_with_wrong_key_raises(self, tmp_path: object) -> None:
        """Decryption with a different key raises InvalidToken."""
        key_path_1 = os.path.join(str(tmp_path), "key1.key")
        key_path_2 = os.path.join(str(tmp_path), "key2.key")

        ct = encrypt_credential("secret", key_path=key_path_1)
        with pytest.raises(InvalidToken):
            decrypt_credential(ct, key_path=key_path_2)


class TestRoundTrip:
    """Tests for encrypt/decrypt round-trip."""

    def test_round_trip_basic(self, key_path: str) -> None:
        """Encrypt then decrypt recovers the original plaintext."""
        original = "my_omada_password"
        ct = encrypt_credential(original, key_path=key_path)
        recovered = decrypt_credential(ct, key_path=key_path)
        assert recovered == original

    def test_round_trip_unicode(self, key_path: str) -> None:
        """Round-trip works with unicode characters."""
        original = "pässwörd_日本語"
        ct = encrypt_credential(original, key_path=key_path)
        recovered = decrypt_credential(ct, key_path=key_path)
        assert recovered == original

    def test_round_trip_special_characters(self, key_path: str) -> None:
        """Round-trip works with special characters."""
        original = "p@$$w0rd!#%^&*()_+-=[]{}|;':\",./<>?"
        ct = encrypt_credential(original, key_path=key_path)
        recovered = decrypt_credential(ct, key_path=key_path)
        assert recovered == original
