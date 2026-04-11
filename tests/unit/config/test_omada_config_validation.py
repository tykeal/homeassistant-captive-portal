# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada controller ID and config validation.

Validates that _validate_controller_id rejects path-injection
attempts and accepts legitimate hex controller IDs.
"""

from __future__ import annotations

import pytest

from captive_portal.config.omada_config import _validate_controller_id


class TestValidateControllerId:
    """Tests for _validate_controller_id."""

    def test_valid_32_char_hex(self) -> None:
        """Accept a typical 32-character hex controller ID."""
        cid = "aabbccdd11223344aabbccdd11223344"
        assert _validate_controller_id(cid) == cid

    def test_valid_24_char_hex(self) -> None:
        """Accept a 24-character hex controller ID."""
        cid = "686982d482171c5562624ad1"
        assert _validate_controller_id(cid) == cid

    def test_valid_16_char_hex(self) -> None:
        """Accept the minimum 16-character hex controller ID."""
        cid = "aabbccdd11223344"
        assert _validate_controller_id(cid) == cid

    def test_valid_64_char_hex(self) -> None:
        """Accept the maximum 64-character hex controller ID."""
        cid = "a" * 64
        assert _validate_controller_id(cid) == cid

    def test_valid_mixed_case_hex(self) -> None:
        """Accept mixed-case hex characters."""
        cid = "aAbBcCdD11223344AaBbCcDd"
        assert _validate_controller_id(cid) == cid

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        cid = "  aabbccdd11223344aabbccdd11223344  "
        assert _validate_controller_id(cid) == "aabbccdd11223344aabbccdd11223344"

    def test_rejects_slash_injection(self) -> None:
        """Reject controller IDs containing forward slashes."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("../../etc/passwd")

    def test_rejects_double_slash_prefix(self) -> None:
        """Reject controller IDs starting with // (host redirect)."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("//evil.com/steal")

    def test_rejects_non_hex_characters(self) -> None:
        """Reject controller IDs with non-hex characters."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("ctrl-test-123-xyz")

    def test_rejects_too_short(self) -> None:
        """Reject controller IDs shorter than 16 characters."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("aabbccdd")

    def test_rejects_too_long(self) -> None:
        """Reject controller IDs longer than 64 characters."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("a" * 65)

    def test_rejects_empty_string(self) -> None:
        """Reject empty string."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("")

    def test_rejects_whitespace_only(self) -> None:
        """Reject whitespace-only string."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("   ")
