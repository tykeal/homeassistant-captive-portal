# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for booking code format validation edge cases."""

from captive_portal.services.booking_code_validator import BookingCodeValidator


class TestBookingCodeFormatValidation:
    """Test booking code format validation per FR-018."""

    def test_slot_code_valid_formats(self) -> None:
        """Slot codes must match ^\d{4,}$."""
        assert BookingCodeValidator.is_valid_slot_code("1234")
        assert BookingCodeValidator.is_valid_slot_code("123456")
        assert BookingCodeValidator.is_valid_slot_code("999999999")

    def test_slot_code_invalid_formats(self) -> None:
        """Invalid slot_code formats."""
        assert not BookingCodeValidator.is_valid_slot_code("123")  # too short
        assert not BookingCodeValidator.is_valid_slot_code("ABC123")  # alphanumeric
        assert not BookingCodeValidator.is_valid_slot_code("12-34")  # special char
        assert not BookingCodeValidator.is_valid_slot_code("")  # empty

    def test_last_four_valid_formats(self) -> None:
        """Last four must match ^\d{4}$."""
        assert BookingCodeValidator.is_valid_last_four("1234")
        assert BookingCodeValidator.is_valid_last_four("0000")
        assert BookingCodeValidator.is_valid_last_four("9999")

    def test_last_four_invalid_formats(self) -> None:
        """Invalid last_four formats."""
        assert not BookingCodeValidator.is_valid_last_four("123")  # too short
        assert not BookingCodeValidator.is_valid_last_four("12345")  # too long
        assert not BookingCodeValidator.is_valid_last_four("ABCD")  # alpha
        assert not BookingCodeValidator.is_valid_last_four("")  # empty

    def test_slot_name_valid_formats(self) -> None:
        """Slot names are opaque strings, non-empty, trimmed, <=128 chars."""
        assert BookingCodeValidator.is_valid_slot_name("Smith")
        assert BookingCodeValidator.is_valid_slot_name("John Doe")
        assert BookingCodeValidator.is_valid_slot_name("Guest #123")
        assert BookingCodeValidator.is_valid_slot_name("A" * 128)  # max length

    def test_slot_name_invalid_formats(self) -> None:
        """Invalid slot_name formats."""
        assert not BookingCodeValidator.is_valid_slot_name("")  # empty
        assert not BookingCodeValidator.is_valid_slot_name("   ")  # whitespace only
        assert not BookingCodeValidator.is_valid_slot_name("A" * 129)  # too long

    def test_slot_name_trimmed(self) -> None:
        """Slot names should be trimmed of leading/trailing whitespace."""
        assert BookingCodeValidator.normalize_slot_name("  Smith  ") == "Smith"
        assert BookingCodeValidator.normalize_slot_name("\tJohn\n") == "John"
