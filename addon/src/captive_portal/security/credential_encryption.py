# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Fernet-based credential encryption for reversible secret storage.

Provides symmetric encryption for credentials (such as the Omada
controller password) that must be stored securely in the database but
also recovered at runtime for API authentication.

The encryption key is stored on the persistent ``/data`` volume and is
auto-generated on first use.  Loss of the key file requires the user to
re-enter the credential — an acceptable trade-off for at-rest security.
"""

from __future__ import annotations

import logging
import os
import stat

from cryptography.fernet import Fernet

logger = logging.getLogger("captive_portal.security")

DEFAULT_KEY_PATH = "/data/.omada_key"


def _load_or_create_key(key_path: str = DEFAULT_KEY_PATH) -> bytes:
    """Load an existing Fernet key or generate a new one.

    When the key file does not exist a fresh 32-byte URL-safe base64
    key is generated, written to *key_path*, and its permissions are
    restricted to owner-only read/write (``0o600``).

    Args:
        key_path: Filesystem path to the key file.

    Returns:
        Raw key bytes suitable for ``Fernet(key)``.
    """
    try:
        with open(key_path, "rb") as fh:
            key_data: bytes = fh.read()
            return key_data
    except FileNotFoundError:
        key: bytes = Fernet.generate_key()
        # Ensure parent directory exists
        parent = os.path.dirname(key_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(key_path, "wb") as fh:
            fh.write(key)
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        logger.info("Generated new Fernet key at %s", key_path)
        return key


def encrypt_credential(plaintext: str, key_path: str = DEFAULT_KEY_PATH) -> str:
    """Encrypt a credential string using Fernet symmetric encryption.

    Args:
        plaintext: The credential to encrypt.
        key_path: Path to the Fernet key file.

    Returns:
        Base64-encoded ciphertext string.

    Raises:
        ValueError: If *plaintext* is empty.
    """
    if not plaintext:
        raise ValueError("Cannot encrypt an empty credential.")
    key = _load_or_create_key(key_path)
    f = Fernet(key)
    token: bytes = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_credential(ciphertext: str, key_path: str = DEFAULT_KEY_PATH) -> str:
    """Decrypt a Fernet-encrypted credential.

    Args:
        ciphertext: Base64-encoded ciphertext.
        key_path: Path to the Fernet key file.

    Returns:
        Decrypted plaintext string.

    Raises:
        ValueError: If *ciphertext* is empty.
        cryptography.fernet.InvalidToken: If the key is wrong or data
            is corrupted.
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt an empty ciphertext.")
    key = _load_or_create_key(key_path)
    f = Fernet(key)
    plaintext_bytes: bytes = f.decrypt(ciphertext.encode("ascii"))
    return plaintext_bytes.decode("utf-8")
