# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for unified code detection (voucher vs booking code)."""

import pytest

from captive_portal.services.unified_code_service import (
    CodeType,
    UnifiedCodeService,
    detect_code_type,
)


class TestUnifiedCodeDetection:
    """Test automatic detection of voucher vs booking code format."""

    def test_detect_voucher_alphanumeric(self) -> None:
        """Voucher codes are alphanumeric A-Z0-9."""
        assert detect_code_type("ABCD1234") == CodeType.VOUCHER
        assert detect_code_type("ABC123XYZ9") == CodeType.VOUCHER
        assert detect_code_type("A1B2") == CodeType.VOUCHER  # min 4 chars

    def test_detect_booking_slot_code_numeric(self) -> None:
        """Booking slot_code is numeric-only, 4+ digits."""
        assert detect_code_type("1234") == CodeType.BOOKING
        assert detect_code_type("123456") == CodeType.BOOKING
        assert detect_code_type("98765432") == CodeType.BOOKING

    def test_detect_booking_slot_name_with_special_chars(self) -> None:
        """Booking slot_name may contain spaces, hyphens, etc."""
        assert detect_code_type("Smith-2025") == CodeType.BOOKING
        assert detect_code_type("John Doe") == CodeType.BOOKING
        assert detect_code_type("Guest #123") == CodeType.BOOKING

    def test_detect_invalid_too_short(self) -> None:
        """Codes shorter than 4 chars are invalid."""
        assert detect_code_type("ABC") == CodeType.INVALID
        assert detect_code_type("12") == CodeType.INVALID
        assert detect_code_type("A") == CodeType.INVALID

    def test_detect_invalid_too_long(self) -> None:
        """Codes longer than 24 chars are invalid."""
        code = "A" * 25
        assert detect_code_type(code) == CodeType.INVALID

    def test_detect_invalid_empty(self) -> None:
        """Empty codes are invalid."""
        assert detect_code_type("") == CodeType.INVALID
        assert detect_code_type("   ") == CodeType.INVALID

    def test_case_insensitive_detection(self) -> None:
        """Code type detection is case-insensitive."""
        assert detect_code_type("abcd1234") == CodeType.VOUCHER
        assert detect_code_type("ABCD1234") == CodeType.VOUCHER
        assert detect_code_type("aBcD1234") == CodeType.VOUCHER


@pytest.mark.asyncio
class TestUnifiedCodeService:
    """Test UnifiedCodeService."""

    async def test_validate_voucher_code(self) -> None:
        """Service validates voucher codes."""
        service = UnifiedCodeService()
        result = await service.validate_code("ABCD1234")
        assert result.code_type == CodeType.VOUCHER
        assert result.normalized_code == "ABCD1234"  # uppercase preserved

    async def test_validate_booking_code(self) -> None:
        """Service validates booking codes."""
        service = UnifiedCodeService()
        result = await service.validate_code("1234")
        assert result.code_type == CodeType.BOOKING
        assert result.normalized_code == "1234"

    async def test_validate_invalid_code(self) -> None:
        """Service rejects invalid codes."""
        service = UnifiedCodeService()
        with pytest.raises(ValueError, match="Invalid authorization code"):
            await service.validate_code("AB")  # too short

    async def test_normalize_case_insensitive(self) -> None:
        """Service normalizes codes to uppercase for vouchers."""
        service = UnifiedCodeService()
        result = await service.validate_code("abcd1234")
        assert result.code_type == CodeType.VOUCHER
        assert result.normalized_code == "ABCD1234"
