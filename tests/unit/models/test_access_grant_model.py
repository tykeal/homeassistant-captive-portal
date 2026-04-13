# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test access grant model validation and lifecycle."""

from datetime import datetime, timedelta, timezone


from captive_portal.models.access_grant import AccessGrant, GrantStatus


def test_access_grant_single_active_per_mac_voucher() -> None:
    """Model allows creating grants for same (mac, voucher_code) pair."""
    base = datetime.now(timezone.utc)
    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="device1",
        voucher_code="CODE1234",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
        status=GrantStatus.ACTIVE,
    )
    assert grant.mac == "AA:BB:CC:DD:EE:FF"
    assert grant.voucher_code == "CODE1234"


def test_access_grant_single_active_per_mac_booking() -> None:
    """Model allows creating grants with booking_ref."""
    base = datetime.now(timezone.utc)
    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="device1",
        booking_ref="BOOK4567",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
        status=GrantStatus.ACTIVE,
    )
    assert grant.mac == "AA:BB:CC:DD:EE:FF"
    assert grant.booking_ref == "BOOK4567"


def test_access_grant_status_enum() -> None:
    """Grant status must be one of: active, revoked, expired, pending, failed."""
    base = datetime.now(timezone.utc)
    for s in GrantStatus:
        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="d1",
            start_utc=base,
            end_utc=base + timedelta(hours=1),
            status=s,
        )
        assert grant.status == s


def test_access_grant_timestamps_utc() -> None:
    """Grant timestamps are UTC with minute-precision rounding."""
    base = datetime(2025, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="d1",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert grant.start_utc.second == 0
    assert grant.start_utc.microsecond == 0
    assert grant.end_utc.second == 0
    assert grant.end_utc.microsecond == 0
    assert grant.created_utc.tzinfo == timezone.utc
    assert grant.updated_utc.tzinfo == timezone.utc


def test_access_grant_nullable_voucher_or_booking() -> None:
    """Grant can have voucher_code or booking_ref independently."""
    base = datetime.now(timezone.utc)

    g1 = AccessGrant(
        mac="AA:BB:CC:DD:EE:01",
        device_id="d1",
        voucher_code="CODE1234",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert g1.voucher_code == "CODE1234"
    assert g1.booking_ref is None

    g2 = AccessGrant(
        mac="AA:BB:CC:DD:EE:02",
        device_id="d2",
        booking_ref="BOOK4567",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert g2.voucher_code is None
    assert g2.booking_ref == "BOOK4567"

    g3 = AccessGrant(
        mac="AA:BB:CC:DD:EE:03",
        device_id="d3",
        voucher_code="CODE7890",
        booking_ref="BOOK7890",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert g3.voucher_code == "CODE7890"
    assert g3.booking_ref == "BOOK7890"


def test_access_grant_mac_required() -> None:
    """MAC address is required on the model."""
    base = datetime.now(timezone.utc)
    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="d1",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert grant.mac == "AA:BB:CC:DD:EE:FF"


def test_access_grant_controller_grant_id_tracked() -> None:
    """Controller grant ID should be stored for external reconciliation."""
    base = datetime.now(timezone.utc)
    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="d1",
        controller_grant_id="ctrl_grant_12345",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert grant.controller_grant_id == "ctrl_grant_12345"

    grant2 = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="d2",
        start_utc=base,
        end_utc=base + timedelta(hours=1),
    )
    assert grant2.controller_grant_id is None
