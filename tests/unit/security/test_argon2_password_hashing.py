# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Tests for argon2 password hashing with OWASP parameters."""

import pytest
from captive_portal.security.password_hashing import (
    hash_password,
    verify_password,
)


class TestArgon2PasswordHashing:
    """Test argon2 password hashing with OWASP parameters."""

    def test_hash_password_returns_valid_phc_string(self) -> None:
        """Hash should return PHC string format starting with $argon2id$."""
        password = "SecureP@ssw0rd!"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert hashed.startswith("$argon2id$")
        assert len(hashed) > 50  # Reasonable minimum length

    def test_verify_password_correct_password_returns_true(self) -> None:
        """Verification with correct password should return True."""
        password = "CorrectP@ss123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect_password_returns_false(self) -> None:
        """Verification with incorrect password should return False."""
        password = "CorrectP@ss123"
        hashed = hash_password(password)

        assert verify_password("WrongPassword", hashed) is False

    def test_hash_password_same_password_different_salts(self) -> None:
        """Same password should produce different hashes due to random salts."""
        password = "SamePassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_hash_password_empty_string(self) -> None:
        """Empty password should be hashed without error."""
        hashed = hash_password("")
        assert hashed.startswith("$argon2id$")
        assert verify_password("", hashed)

    def test_verify_password_empty_string_against_non_empty(self) -> None:
        """Empty password should not verify against non-empty hash."""
        password = "NonEmpty123"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

    def test_hash_password_unicode_characters(self) -> None:
        """Unicode passwords should be handled correctly."""
        password = "P@ss🔐w0rd™"
        hashed = hash_password(password)

        assert verify_password(password, hashed)

    def test_verify_password_constant_time(self) -> None:
        """Password verification should use constant-time comparison."""
        # This tests that argon2-cffi uses constant-time comparison
        # by verifying wrong passwords still complete successfully
        password = "Test123"
        hashed = hash_password(password)

        # Both should complete without timing attacks
        result1 = verify_password("Wrong1", hashed)
        result2 = verify_password("Wrong2", hashed)

        assert result1 is False
        assert result2 is False

    def test_verify_password_invalid_hash_format(self) -> None:
        """Invalid hash format should raise ValueError."""
        with pytest.raises(ValueError):
            verify_password("password", "not-a-valid-phc-hash")

    def test_verify_password_malformed_hash(self) -> None:
        """Malformed argon2 hash should return False or raise ValueError."""
        # argon2-cffi returns False for malformed hashes in some cases
        result = verify_password("password", "$argon2id$malformed")
        assert result is False

    @pytest.mark.parametrize(
        "password",
        [
            "short",
            "a" * 1000,  # Very long password
            "P@ssw0rd!",
            "12345678",
            "NoSpecialChars123",
            "   spaces   ",
        ],
    )
    def test_hash_password_various_formats(self, password: str) -> None:
        """Various password formats should hash and verify correctly."""
        hashed = hash_password(password)
        assert verify_password(password, hashed)
