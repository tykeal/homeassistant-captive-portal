# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada controller ID and config validation.

Validates that _validate_controller_id rejects path-injection
attempts and accepts legitimate hex controller IDs.
"""

from __future__ import annotations

import logging

import pytest

from captive_portal.config import omada_config
from captive_portal.config.omada_config import _validate_controller_id, build_omada_config
from captive_portal.models.omada_config import OmadaConfig


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
        """Accept a 16-character hex controller ID."""
        cid = "aabbccdd11223344"
        assert _validate_controller_id(cid) == cid

    def test_valid_12_char_hex(self) -> None:
        """Accept the minimum 12-character hex controller ID."""
        cid = "aabbccdd1122"
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
        """Reject controller IDs shorter than 12 characters."""
        with pytest.raises(ValueError, match="Invalid controller ID"):
            _validate_controller_id("aabbccdd112")

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


@pytest.mark.asyncio
async def test_forced_legacy_ignores_broken_openapi_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced legacy selection must not decrypt inactive OpenAPI secrets."""

    def decrypt(ciphertext: str) -> str:
        """Return the legacy password and fail inactive OpenAPI secrets."""
        if ciphertext == "legacy-cipher":
            return "legacy-pass"
        raise ValueError("broken secret")

    monkeypatch.setattr(omada_config, "decrypt_credential", decrypt)

    runtime = await build_omada_config(
        OmadaConfig(
            controller_url="https://ctrl.test:8043",
            username="operator",
            encrypted_password="legacy-cipher",
            client_id="client-id",
            encrypted_client_secret="broken-openapi-cipher",
            openapi_mode="legacy",
            controller_id="0123456789ab",
        ),
        logging.getLogger(__name__),
    )

    assert runtime is not None
    assert runtime.selected_backend == "legacy"
