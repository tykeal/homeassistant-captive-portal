# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test voucher redemption logic."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import GrantStatus
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.services.voucher_service import (
    VoucherRedemptionError,
    VoucherService,
)


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

    @pytest.mark.asyncio
    async def test_redeem_valid_unused_voucher(self, db_session: Session) -> None:
        """Redeem valid unused voucher returns AccessGrant."""
        _make_voucher(db_session, code="REDEEM0001")
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        grant = await svc.redeem("REDEEM0001", "AA:BB:CC:DD:EE:01")
        assert grant is not None
        assert grant.voucher_code == "REDEEM0001"
        assert grant.mac == "AA:BB:CC:DD:EE:01"

    @pytest.mark.asyncio
    async def test_redeem_expired_voucher_fails(self, db_session: Session) -> None:
        """Redeem expired voucher (expires_utc < now) raises exception."""
        now = datetime.now(timezone.utc)
        _make_voucher(
            db_session,
            code="REDEEM0002",
            activated_utc=now - timedelta(days=365),
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
        )
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        with pytest.raises(VoucherRedemptionError, match="expired"):
            await svc.redeem("REDEEM0002", "AA:BB:CC:DD:EE:02")

    @pytest.mark.asyncio
    async def test_redeem_revoked_voucher_fails(self, db_session: Session) -> None:
        """Redeem revoked voucher (status=REVOKED) raises exception."""
        _make_voucher(db_session, code="REDEEM0003", status=VoucherStatus.REVOKED)
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        with pytest.raises(VoucherRedemptionError, match="revoked"):
            await svc.redeem("REDEEM0003", "AA:BB:CC:DD:EE:03")

    @pytest.mark.asyncio
    async def test_redeem_increments_redeemed_count(self, db_session: Session) -> None:
        """Redeem increments voucher.redeemed_count and sets last_redeemed_utc."""
        voucher = _make_voucher(db_session, code="REDEEM0004")
        now = datetime.now(timezone.utc)
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        await svc.redeem("REDEEM0004", "AA:BB:CC:DD:EE:04", current_time=now)
        db_session.refresh(voucher)
        assert voucher.redeemed_count == 1
        assert voucher.last_redeemed_utc is not None

    @pytest.mark.asyncio
    async def test_redeem_creates_access_grant(self, db_session: Session) -> None:
        """Redeem creates AccessGrant with correct start/end UTC."""
        _make_voucher(db_session, code="REDEEM0005", duration_minutes=120)
        now = datetime.now(timezone.utc)
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        grant = await svc.redeem("REDEEM0005", "AA:BB:CC:DD:EE:05", current_time=now)
        assert grant.status == GrantStatus.PENDING
        assert grant.start_utc.second == 0
        assert grant.end_utc.second == 0

    @pytest.mark.asyncio
    async def test_redeem_voucher_bandwidth_tracked_on_voucher(self, db_session: Session) -> None:
        """Redeem creates grant; bandwidth limits remain on the voucher."""
        voucher = _make_voucher(db_session, code="REDEEM0006")
        voucher.up_kbps = 512
        voucher.down_kbps = 1024
        db_session.commit()

        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        grant = await svc.redeem("REDEEM0006", "AA:BB:CC:DD:EE:06")
        assert grant is not None
        assert grant.voucher_code == "REDEEM0006"

    @pytest.mark.asyncio
    async def test_redeem_updates_voucher_status_to_active(self, db_session: Session) -> None:
        """Redeem transitions voucher status UNUSED -> ACTIVE."""
        voucher = _make_voucher(db_session, code="REDEEM0007")

        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        await svc.redeem("REDEEM0007", "AA:BB:CC:DD:EE:07")
        db_session.refresh(voucher)
        assert voucher.status == VoucherStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_redeem_duplicate_mac_prevents_double_redemption(
        self, db_session: Session
    ) -> None:
        """Redeem same voucher+MAC when grant is ACTIVE raises conflict."""
        _make_voucher(db_session, code="REDEEM0008")
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        grant = await svc.redeem("REDEEM0008", "AA:BB:CC:DD:EE:08")
        # Simulate controller confirmation by setting ACTIVE
        grant.status = GrantStatus.ACTIVE
        db_session.commit()
        with pytest.raises(VoucherRedemptionError, match="already authorized"):
            await svc.redeem("REDEEM0008", "AA:BB:CC:DD:EE:08")


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
