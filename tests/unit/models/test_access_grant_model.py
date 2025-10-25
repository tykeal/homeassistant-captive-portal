# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test access grant model validation and lifecycle."""

import pytest


def test_access_grant_single_active_per_mac_voucher() -> None:
    """Only one active grant per (mac, voucher_code) tuple allowed."""
    # GIVEN: existing active grant for mac="AA:BB:CC:DD:EE:FF", voucher="CODE123"
    # WHEN: attempting to create second active grant with same tuple
    # THEN: constraint violation or business rule rejection
    pytest.skip("Model not implemented yet")


def test_access_grant_single_active_per_mac_booking() -> None:
    """Only one active grant per (mac, booking_ref) tuple allowed."""
    # GIVEN: existing active grant for mac="AA:BB:CC:DD:EE:FF", booking_ref="BOOK456"
    # WHEN: attempting to create second active grant with same tuple
    # THEN: constraint violation or business rule rejection
    pytest.skip("Model not implemented yet")


def test_access_grant_status_enum() -> None:
    """Grant status must be one of: active, revoked, expired, pending."""
    # GIVEN: valid and invalid status values
    # WHEN: creating grant
    # THEN: valid accepted, invalid rejected
    pytest.skip("Model not implemented yet")


def test_access_grant_timestamps_utc() -> None:
    """All grant timestamps (start_utc, end_utc, created_utc, updated_utc) must be UTC."""
    # GIVEN: grant with timestamps
    # WHEN: persisting and retrieving
    # THEN: timestamps remain UTC, minute-precision rounding applied
    pytest.skip("Model not implemented yet")


def test_access_grant_nullable_voucher_or_booking() -> None:
    """Grant can have voucher_code OR booking_ref (both nullable, at least one required)."""
    # GIVEN: grant with only voucher_code OR only booking_ref
    # WHEN: creating grant
    # THEN: accepted; both NULL rejected
    pytest.skip("Model not implemented yet")


def test_access_grant_mac_required() -> None:
    """MAC address is required (session_token is fallback)."""
    # GIVEN: grant without mac and without session_token
    # WHEN: creating grant
    # THEN: validation error
    pytest.skip("Model not implemented yet")


def test_access_grant_controller_grant_id_tracked() -> None:
    """Controller grant ID should be stored for external system reconciliation."""
    # GIVEN: grant with controller_grant_id
    # WHEN: updating or revoking
    # THEN: controller_grant_id used for API calls
    pytest.skip("Model not implemented yet")
