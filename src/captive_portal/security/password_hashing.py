# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Password hashing using argon2 with OWASP parameters."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

# OWASP recommended parameters for argon2id
# m=65536 (64 MiB memory), t=3 iterations, p=4 parallelism
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,  # argon2id
)


def hash_password(password: str) -> str:
    """
    Hash a password using argon2id with OWASP parameters.

    Args:
        password: Plain text password to hash

    Returns:
        PHC string format hash starting with $argon2id$

    Raises:
        ValueError: If password hashing fails
    """
    try:
        return _ph.hash(password)
    except Exception as e:
        raise ValueError(f"Password hashing failed: {e}") from e


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its hash using constant-time comparison.

    Args:
        password: Plain text password to verify
        password_hash: PHC format hash string

    Returns:
        True if password matches hash, False otherwise

    Raises:
        ValueError: If hash format is invalid
    """
    try:
        _ph.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError):
        return False
    except (InvalidHash, Exception) as e:
        raise ValueError(f"Invalid password hash format: {e}") from e
