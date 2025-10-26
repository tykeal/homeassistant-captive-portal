# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test voucher model validation and duration calculations."""

import pytest


def test_voucher_code_validation_valid() -> None:
    """Voucher code with A-Z0-9 chars only should be valid."""
    # GIVEN: valid voucher code
    # WHEN: creating voucher
    # THEN: no validation error
    pytest.skip("Model not implemented yet")


def test_voucher_code_validation_invalid_chars() -> None:
    """Voucher code with invalid chars should fail validation."""
    # GIVEN: code with lowercase or special chars
    # WHEN: creating voucher
    # THEN: validation error raised
    pytest.skip("Model not implemented yet")


def test_voucher_code_length_bounds() -> None:
    """Voucher code length must be within configured bounds (4-24)."""
    # GIVEN: codes below min or above max
    # WHEN: creating voucher
    # THEN: validation error raised
    pytest.skip("Model not implemented yet")


def test_voucher_expires_utc_derived() -> None:
    """Voucher expires_utc should be created_utc + duration_minutes."""
    # GIVEN: voucher with created_utc and duration_minutes
    # WHEN: accessing expires_utc
    # THEN: equals created_utc + duration (floored to minute)
    pytest.skip("Model not implemented yet")


def test_voucher_status_enum() -> None:
    """Voucher status must be one of defined enum values."""
    # GIVEN: valid status values (unused, active, expired, revoked)
    # WHEN: creating voucher
    # THEN: accepted; invalid status rejected
    pytest.skip("Model not implemented yet")


def test_voucher_bandwidth_nullable() -> None:
    """Bandwidth fields (up_kbps, down_kbps) should be nullable with CHECK > 0."""
    # GIVEN: voucher with NULL or positive bandwidth
    # WHEN: creating voucher
    # THEN: accepted; zero/negative rejected
    pytest.skip("Model not implemented yet")


def test_voucher_booking_ref_case_sensitive() -> None:
    """Booking reference should be stored and matched case-sensitively."""
    # GIVEN: voucher with booking_ref "ABC123"
    # WHEN: querying by "abc123"
    # THEN: no match (case-sensitive)
    pytest.skip("Model not implemented yet")


def test_voucher_redeemed_count_increments() -> None:
    """Redeemed count should increment on each redemption."""
    # GIVEN: voucher with redeemed_count=0
    # WHEN: redeeming voucher
    # THEN: redeemed_count increments, last_redeemed_utc updated
    pytest.skip("Model not implemented yet")
