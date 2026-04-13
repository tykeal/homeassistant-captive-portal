# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for end-to-end authorize flow (voucher -> grant)."""

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
) -> Voucher:
    """Create and persist a voucher for testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return voucher


class TestAuthorizeEndToEnd:
    """Test complete authorize flow from voucher redemption to grant creation."""

    @pytest.mark.asyncio
    async def test_successful_voucher_redemption_creates_grant(
        self,
        db_session: Session,
    ) -> None:
        """Redeeming valid voucher should create grant with PENDING status."""
        _make_voucher(db_session, code="AUTH000001")
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        grant = await svc.redeem("AUTH000001", "AA:BB:CC:DD:EE:01")

        assert grant is not None
        assert grant.status == GrantStatus.PENDING
        assert grant.voucher_code == "AUTH000001"
        assert grant.mac == "AA:BB:CC:DD:EE:01"

    @pytest.mark.asyncio
    async def test_redemption_updates_voucher_state(self, db_session: Session) -> None:
        """Redemption updates voucher to ACTIVE and sets activated_utc."""
        voucher = _make_voucher(db_session, code="AUTH000002")
        assert voucher.activated_utc is None

        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        await svc.redeem("AUTH000002", "AA:BB:CC:DD:EE:02")

        db_session.refresh(voucher)
        assert voucher.status == VoucherStatus.ACTIVE
        assert voucher.activated_utc is not None
        assert voucher.redeemed_count == 1

    @pytest.mark.asyncio
    async def test_revoked_voucher_redemption_rejected(self, db_session: Session) -> None:
        """Redeeming a revoked voucher should raise an error."""
        _make_voucher(db_session, code="AUTH000003", status=VoucherStatus.REVOKED)
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        with pytest.raises(VoucherRedemptionError, match="revoked"):
            await svc.redeem("AUTH000003", "AA:BB:CC:DD:EE:03")

    @pytest.mark.asyncio
    async def test_expired_voucher_redemption_rejected(self, db_session: Session) -> None:
        """Redeeming an expired voucher should raise an error."""
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="AUTH000004",
            status=VoucherStatus.ACTIVE,
        )
        voucher.activated_utc = now - timedelta(days=365)
        voucher.redeemed_count = 1
        db_session.commit()

        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        with pytest.raises(VoucherRedemptionError, match="expired"):
            await svc.redeem("AUTH000004", "AA:BB:CC:DD:EE:04")

    @pytest.mark.asyncio
    async def test_duplicate_mac_authorization_rejected(self, db_session: Session) -> None:
        """Already active grant for same voucher+MAC blocks re-redemption."""
        _make_voucher(db_session, code="AUTH000005")
        repo = VoucherRepository(db_session)
        grant_repo = AccessGrantRepository(db_session)
        svc = VoucherService(session=db_session, voucher_repo=repo, grant_repo=grant_repo)
        grant = await svc.redeem("AUTH000005", "AA:BB:CC:DD:EE:05")
        # Simulate controller confirmation
        grant.status = GrantStatus.ACTIVE
        db_session.commit()

        with pytest.raises(VoucherRedemptionError, match="already authorized"):
            await svc.redeem("AUTH000005", "AA:BB:CC:DD:EE:05")
