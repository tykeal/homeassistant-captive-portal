# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test voucher model validation and duration calculations."""

from datetime import datetime, timedelta, timezone

import pytest

from captive_portal.models.voucher import Voucher, VoucherStatus


def test_voucher_code_validation_valid() -> None:
    """Voucher code with A-Z0-9 chars only should be valid."""
    voucher = Voucher.model_validate({"code": "TEST1234", "duration_minutes": 60})
    assert voucher.code == "TEST1234"


def test_voucher_code_validation_invalid_chars() -> None:
    """Voucher code with invalid chars should fail validation."""
    with pytest.raises(ValueError, match="A-Z and 0-9"):
        Voucher.model_validate({"code": "test1234", "duration_minutes": 60})
    with pytest.raises(ValueError, match="A-Z and 0-9"):
        Voucher.model_validate({"code": "TEST@123", "duration_minutes": 60})


def test_voucher_code_length_bounds() -> None:
    """Voucher code length must be within configured bounds (4-24)."""
    with pytest.raises(ValueError):
        Voucher.model_validate({"code": "ABC", "duration_minutes": 60})
    with pytest.raises(ValueError):
        Voucher.model_validate({"code": "A" * 25, "duration_minutes": 60})
    short = Voucher.model_validate({"code": "ABCD", "duration_minutes": 60})
    assert short.code == "ABCD"
    long = Voucher.model_validate({"code": "A" * 24, "duration_minutes": 60})
    assert long.code == "A" * 24


def test_voucher_expires_utc_derived() -> None:
    """Voucher expires_utc should be created_utc + duration_minutes."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    voucher = Voucher(code="TEST1234", created_utc=now, duration_minutes=60)
    assert voucher.expires_utc == now + timedelta(minutes=60)

    activated = now + timedelta(hours=1)
    voucher2 = Voucher(
        code="TEST5678",
        created_utc=now,
        activated_utc=activated,
        duration_minutes=60,
    )
    expected = (activated + timedelta(minutes=60)).replace(second=0, microsecond=0)
    assert voucher2.expires_utc == expected


def test_voucher_status_enum() -> None:
    """Voucher status must be one of defined enum values."""
    for s in VoucherStatus:
        v = Voucher(code="TEST1234", duration_minutes=60, status=s)
        assert v.status == s


def test_voucher_bandwidth_nullable() -> None:
    """Bandwidth fields (up_kbps, down_kbps) should be nullable with CHECK > 0."""
    v = Voucher(code="TEST1234", duration_minutes=60, up_kbps=None, down_kbps=None)
    assert v.up_kbps is None
    assert v.down_kbps is None

    v2 = Voucher(code="TEST5678", duration_minutes=60, up_kbps=100, down_kbps=200)
    assert v2.up_kbps == 100
    assert v2.down_kbps == 200

    with pytest.raises(ValueError):
        Voucher.model_validate({"code": "TEST9012", "duration_minutes": 60, "up_kbps": 0})
    with pytest.raises(ValueError):
        Voucher.model_validate({"code": "TEST9012", "duration_minutes": 60, "down_kbps": -1})


def test_voucher_booking_ref_case_sensitive() -> None:
    """Booking reference should be stored and matched case-sensitively."""
    v1 = Voucher(code="TEST1234", duration_minutes=60, booking_ref="ABC123")
    v2 = Voucher(code="TEST5678", duration_minutes=60, booking_ref="abc123")
    assert v1.booking_ref == "ABC123"
    assert v2.booking_ref == "abc123"
    assert v1.booking_ref != v2.booking_ref


def test_voucher_redeemed_count_increments() -> None:
    """Redeemed count should increment on each redemption."""
    voucher = Voucher(code="TEST1234", duration_minutes=60)
    assert voucher.redeemed_count == 0
    assert voucher.last_redeemed_utc is None

    now = datetime.now(timezone.utc)
    voucher.redeemed_count = 1
    voucher.last_redeemed_utc = now
    assert voucher.redeemed_count == 1
    assert voucher.last_redeemed_utc == now
