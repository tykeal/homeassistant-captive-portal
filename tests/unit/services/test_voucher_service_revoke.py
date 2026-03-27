# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for voucher service error types and revoke logic (T002, T006)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import VoucherRepository
from captive_portal.services.voucher_service import (
    VoucherExpiredError,
    VoucherNotFoundError,
    VoucherRedeemedError,
    VoucherService,
)


def _make_voucher(
    session: Session,
    *,
    code: str = "TESTCODE01",
    duration_minutes: int = 60,
    status: VoucherStatus = VoucherStatus.UNUSED,
    redeemed_count: int = 0,
    booking_ref: str | None = None,
) -> Voucher:
    """Create and persist a voucher for testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
        booking_ref=booking_ref,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return voucher


class TestErrorTypes:
    """T002: Error types are importable and well-formed."""

    def test_voucher_not_found_error(self) -> None:
        """Verify VoucherNotFoundError stores the code and is an Exception."""
        err = VoucherNotFoundError("ABC123")
        assert isinstance(err, Exception)
        assert err.code == "ABC123"
        assert "ABC123" in str(err)

    def test_voucher_expired_error(self) -> None:
        """Verify VoucherExpiredError stores the code and is an Exception."""
        err = VoucherExpiredError("DEF456")
        assert isinstance(err, Exception)
        assert err.code == "DEF456"
        assert "DEF456" in str(err)

    def test_voucher_redeemed_error(self) -> None:
        """Verify VoucherRedeemedError stores the code and is an Exception."""
        err = VoucherRedeemedError("GHI789")
        assert isinstance(err, Exception)
        assert err.code == "GHI789"
        assert "GHI789" in str(err)


class TestVoucherServiceRevoke:
    """T006: VoucherService.revoke() unit tests."""

    @pytest.mark.asyncio
    async def test_revoke_unused_voucher(self, db_session: Session) -> None:
        """Verify revoking an unused voucher sets status to REVOKED."""
        _make_voucher(db_session, code="REVUNUSED1")
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        result = await service.revoke("REVUNUSED1")
        assert result.status == VoucherStatus.REVOKED
        db_session.delete(result)
        db_session.commit()

    @pytest.mark.asyncio
    async def test_revoke_active_voucher(self, db_session: Session) -> None:
        """Verify revoking an active voucher sets status to REVOKED."""
        _make_voucher(db_session, code="REVACTIV01", status=VoucherStatus.ACTIVE)
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        result = await service.revoke("REVACTIV01")
        assert result.status == VoucherStatus.REVOKED
        db_session.delete(result)
        db_session.commit()

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_is_idempotent(self, db_session: Session) -> None:
        """Verify revoking an already-revoked voucher is idempotent."""
        _make_voucher(db_session, code="REVIDMPT01", status=VoucherStatus.REVOKED)
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        result = await service.revoke("REVIDMPT01")
        assert result.status == VoucherStatus.REVOKED
        db_session.delete(result)
        db_session.commit()

    @pytest.mark.asyncio
    async def test_revoke_not_found_raises(self, db_session: Session) -> None:
        """Verify revoking a nonexistent voucher raises VoucherNotFoundError."""
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        with pytest.raises(VoucherNotFoundError):
            await service.revoke("NONEXIST99")

    @pytest.mark.asyncio
    async def test_revoke_expired_voucher_raises(self, db_session: Session) -> None:
        """Verify revoking an expired voucher raises VoucherExpiredError."""
        voucher = _make_voucher(db_session, code="REVEXPRD01")
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        future = datetime.now(timezone.utc) + timedelta(days=365)
        with pytest.raises(VoucherExpiredError):
            await service.revoke("REVEXPRD01", current_time=future)
        db_session.delete(voucher)
        db_session.commit()
