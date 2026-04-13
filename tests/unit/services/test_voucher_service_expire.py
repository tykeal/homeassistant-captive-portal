# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for lazy voucher expiration logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import VoucherRepository
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


class TestExpireStaleVouchers:
    """Tests for VoucherService.expire_stale_vouchers()."""

    def test_active_past_expiry_becomes_expired(self, db_session: Session) -> None:
        """ACTIVE voucher past expires_utc transitions to EXPIRED."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="EXPSTALE01",
            duration_minutes=1,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=2),
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([voucher])
        assert count == 1
        assert voucher.status == VoucherStatus.EXPIRED

    def test_active_not_yet_expired_stays_active(self, db_session: Session) -> None:
        """ACTIVE voucher still within duration stays ACTIVE."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="EXPSTALE02",
            duration_minutes=60,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=10),
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([voucher])
        assert count == 0
        assert voucher.status == VoucherStatus.ACTIVE

    def test_unused_voucher_not_expired(self, db_session: Session) -> None:
        """UNUSED voucher is never transitioned to EXPIRED."""
        voucher = _make_voucher(
            db_session,
            code="EXPSTALE03",
            duration_minutes=1,
            status=VoucherStatus.UNUSED,
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        future = datetime.now(timezone.utc) + timedelta(days=365)
        count = svc.expire_stale_vouchers([voucher], current_time=future)
        assert count == 0
        assert voucher.status == VoucherStatus.UNUSED

    def test_revoked_voucher_stays_revoked(self, db_session: Session) -> None:
        """REVOKED voucher is not changed to EXPIRED."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="EXPSTALE04",
            duration_minutes=1,
            status=VoucherStatus.REVOKED,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=10),
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([voucher])
        assert count == 0
        assert voucher.status == VoucherStatus.REVOKED

    def test_already_expired_voucher_not_counted(self, db_session: Session) -> None:
        """Voucher already EXPIRED is not counted again."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="EXPSTALE05",
            duration_minutes=1,
            status=VoucherStatus.EXPIRED,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=10),
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([voucher])
        assert count == 0
        assert voucher.status == VoucherStatus.EXPIRED

    def test_mixed_list_only_expires_stale_active(self, db_session: Session) -> None:
        """Only stale ACTIVE vouchers transition in a mixed list."""
        now = datetime.now(timezone.utc)
        stale = _make_voucher(
            db_session,
            code="EXPMIX0001",
            duration_minutes=1,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=5),
        )
        fresh = _make_voucher(
            db_session,
            code="EXPMIX0002",
            duration_minutes=60,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=5),
        )
        unused = _make_voucher(
            db_session,
            code="EXPMIX0003",
            duration_minutes=1,
            status=VoucherStatus.UNUSED,
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([stale, fresh, unused])
        assert count == 1
        assert stale.status == VoucherStatus.EXPIRED
        assert fresh.status == VoucherStatus.ACTIVE
        assert unused.status == VoucherStatus.UNUSED

    def test_empty_list_returns_zero(self, db_session: Session) -> None:
        """Empty voucher list returns 0 with no side effects."""
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([])
        assert count == 0


class TestExpireStatusChangedUtc:
    """T003: status_changed_utc timestamp on expire transitions."""

    def test_expire_sets_status_changed_utc(self, db_session: Session) -> None:
        """ACTIVE→EXPIRED sets status_changed_utc to current time."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="EXPCHG0001",
            duration_minutes=1,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=5),
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        svc.expire_stale_vouchers([voucher], current_time=now)
        assert voucher.status == VoucherStatus.EXPIRED
        assert voucher.status_changed_utc is not None
        assert voucher.status_changed_utc == now

    def test_expire_does_not_overwrite_already_expired(self, db_session: Session) -> None:
        """Already-EXPIRED vouchers do NOT get status_changed_utc overwritten."""
        original_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="EXPNOW0001",
            duration_minutes=1,
            status=VoucherStatus.EXPIRED,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=10),
        )
        # Manually set status_changed_utc to simulate existing value
        voucher.status_changed_utc = original_time
        db_session.commit()

        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        count = svc.expire_stale_vouchers([voucher], current_time=now)
        assert count == 0
        # SQLite strips tzinfo on round-trip — compare naive
        naive_original = original_time.replace(tzinfo=None)
        result_ts = voucher.status_changed_utc
        if result_ts is not None and result_ts.tzinfo is not None:
            result_ts = result_ts.replace(tzinfo=None)
        assert result_ts == naive_original

    def test_unused_voucher_keeps_null_status_changed(self, db_session: Session) -> None:
        """UNUSED vouchers remain with NULL status_changed_utc."""
        voucher = _make_voucher(
            db_session,
            code="EXPNUL0001",
            duration_minutes=1,
            status=VoucherStatus.UNUSED,
        )
        svc = VoucherService(
            session=db_session,
            voucher_repo=VoucherRepository(db_session),
        )
        future = datetime.now(timezone.utc) + timedelta(days=365)
        svc.expire_stale_vouchers([voucher], current_time=future)
        assert voucher.status_changed_utc is None


class TestRedeemPersistsExpired:
    """Verify redeem() persists EXPIRED before raising."""

    @pytest.mark.asyncio
    async def test_redeem_expired_sets_status(self, db_session: Session) -> None:
        """Redeem on expired voucher sets status to EXPIRED."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="RDMEXP0001",
            duration_minutes=1,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=5),
        )
        repo = VoucherRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo)
        from captive_portal.services.voucher_service import (
            VoucherRedemptionError,
        )

        with pytest.raises(VoucherRedemptionError, match="expired"):
            await svc.redeem("RDMEXP0001", "AA:BB:CC:DD:EE:01")
        db_session.refresh(voucher)
        assert voucher.status == VoucherStatus.EXPIRED


class TestRevokePersistsExpired:
    """Verify revoke() persists EXPIRED before raising."""

    @pytest.mark.asyncio
    async def test_revoke_expired_sets_status(self, db_session: Session) -> None:
        """Revoke on expired voucher sets status to EXPIRED."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="RVKEXP0001",
            duration_minutes=1,
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
            activated_utc=now - timedelta(minutes=5),
        )
        repo = VoucherRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo)
        from captive_portal.services.voucher_service import (
            VoucherExpiredError,
        )

        with pytest.raises(VoucherExpiredError):
            await svc.revoke("RVKEXP0001")
        db_session.refresh(voucher)
        assert voucher.status == VoucherStatus.EXPIRED
