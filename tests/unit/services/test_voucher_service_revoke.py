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
    activated_utc: datetime | None = None,
) -> Voucher:
    """Create and persist a voucher for testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
        booking_ref=booking_ref,
        activated_utc=activated_utc,
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
        now = datetime.now(timezone.utc)
        voucher = _make_voucher(
            db_session,
            code="REVEXPRD01",
            activated_utc=now,
        )
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        future = now + timedelta(days=365)
        with pytest.raises(VoucherExpiredError):
            await service.revoke("REVEXPRD01", current_time=future)
        db_session.delete(voucher)
        db_session.commit()


class TestRevokeStatusChangedUtc:
    """T004: status_changed_utc timestamp on revoke transitions."""

    @pytest.mark.asyncio
    async def test_revoke_unused_sets_status_changed_utc(self, db_session: Session) -> None:
        """UNUSED→REVOKED sets status_changed_utc."""
        now = datetime.now(timezone.utc)
        _make_voucher(db_session, code="RVKCHG0001")
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        result = await service.revoke("RVKCHG0001", current_time=now)
        assert result.status == VoucherStatus.REVOKED
        assert result.status_changed_utc is not None
        # SQLite strips tzinfo — compare naive
        result_ts = (
            result.status_changed_utc.replace(tzinfo=None)
            if result.status_changed_utc.tzinfo
            else result.status_changed_utc
        )
        assert result_ts == now.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_revoke_active_sets_status_changed_utc(self, db_session: Session) -> None:
        """ACTIVE→REVOKED sets status_changed_utc."""
        now = datetime.now(timezone.utc)
        _make_voucher(db_session, code="RVKACT0001", status=VoucherStatus.ACTIVE)
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        result = await service.revoke("RVKACT0001", current_time=now)
        assert result.status == VoucherStatus.REVOKED
        result_ts = (
            result.status_changed_utc.replace(tzinfo=None)
            if result.status_changed_utc and result.status_changed_utc.tzinfo
            else result.status_changed_utc
        )
        assert result_ts == now.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_revoke_expired_active_sets_status_changed_utc(self, db_session: Session) -> None:
        """ACTIVE→EXPIRED (via revoke) sets status_changed_utc."""
        now = datetime.now(timezone.utc)
        _make_voucher(
            db_session,
            code="RVKEXP0002",
            activated_utc=now - timedelta(days=365),
        )
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        future = now + timedelta(days=365)
        with pytest.raises(VoucherExpiredError):
            await service.revoke("RVKEXP0002", current_time=future)
        voucher = repo.get_by_code("RVKEXP0002")
        assert voucher is not None
        assert voucher.status == VoucherStatus.EXPIRED
        result_ts = voucher.status_changed_utc
        if result_ts is not None and result_ts.tzinfo is not None:
            result_ts = result_ts.replace(tzinfo=None)
        assert result_ts == future.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_does_not_overwrite(self, db_session: Session) -> None:
        """Already-REVOKED voucher does NOT get status_changed_utc overwritten."""
        original_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        _make_voucher(db_session, code="RVKNOW0001", status=VoucherStatus.REVOKED)
        # Manually set status_changed_utc

        voucher = db_session.get(Voucher, "RVKNOW0001")
        assert voucher is not None
        voucher.status_changed_utc = original_time
        db_session.commit()

        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        result = await service.revoke("RVKNOW0001")
        assert result.status == VoucherStatus.REVOKED
        result_ts = result.status_changed_utc
        if result_ts is not None and result_ts.tzinfo is not None:
            result_ts = result_ts.replace(tzinfo=None)
        assert result_ts == original_time.replace(tzinfo=None)
