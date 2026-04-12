# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test voucher redemption logic."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.services.voucher_service import VoucherService


def _make_voucher(
    session: Session,
    *,
    code: str = "TESTCODE01",
    duration_minutes: int = 60,
    status: VoucherStatus = VoucherStatus.UNUSED,
    redeemed_count: int = 0,
    activated_utc: datetime | None = None,
) -> Voucher:
    """Create and persist a voucher for testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
        activated_utc=activated_utc,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return voucher


class TestVoucherServiceRedeem:
    """Test VoucherService.redeem() method."""

    def test_redeem_valid_unused_voucher(self) -> None:
        """Redeem valid unused voucher returns AccessGrant."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_expired_voucher_fails(self) -> None:
        """Redeem expired voucher (expires_utc < now) raises exception."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_revoked_voucher_fails(self) -> None:
        """Redeem revoked voucher (status=REVOKED) raises exception."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_increments_redeemed_count(self) -> None:
        """Redeem increments voucher.redeemed_count and sets last_redeemed_utc."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_creates_access_grant(self) -> None:
        """Redeem creates AccessGrant with correct start/end UTC."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_applies_bandwidth_limits_to_grant(self) -> None:
        """Redeem applies voucher up/down kbps to AccessGrant."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_updates_voucher_status_to_active(self) -> None:
        """Redeem transitions voucher status UNUSED -> ACTIVE."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_emits_audit_log(self) -> None:
        """Redeem emits audit log with voucher_code, MAC, outcome."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")

    def test_redeem_duplicate_mac_prevents_double_redemption(self) -> None:
        """Redeem same voucher+MAC twice raises conflict."""
        pytest.skip("Phase 2 TDD: awaiting VoucherService implementation")


class TestRedeemActivationExpiry:
    """Verify activation-based expiry semantics on first redemption."""

    @pytest.mark.asyncio
    async def test_first_redeem_sets_activated_utc(self, db_session: Session) -> None:
        """First redemption sets activated_utc to current_time."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(db_session, code="ACTIV00001")
        assert voucher.activated_utc is None

        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(
            session=db_session,
            voucher_repo=repo,
            grant_repo=grant_repo,
        )
        await svc.redeem("ACTIV00001", "AA:BB:CC:DD:EE:01", current_time=now)

        db_session.refresh(voucher)
        assert voucher.activated_utc is not None
        # SQLite strips tzinfo; compare naive values
        assert voucher.activated_utc.replace(tzinfo=None) == now.replace(tzinfo=None)

        db_session.delete(voucher)
        db_session.commit()

    @pytest.mark.asyncio
    async def test_expires_utc_based_on_activated_utc(self, db_session: Session) -> None:
        """After redemption, expires_utc equals activated + duration."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(db_session, code="ACTIV00002", duration_minutes=120)

        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(
            session=db_session,
            voucher_repo=repo,
            grant_repo=grant_repo,
        )
        await svc.redeem("ACTIV00002", "AA:BB:CC:DD:EE:02", current_time=now)

        db_session.refresh(voucher)
        expected = (now + timedelta(minutes=120)).replace(second=0, microsecond=0)
        assert voucher.expires_utc == expected

        db_session.delete(voucher)
        db_session.commit()
