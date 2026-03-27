# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for voucher repository delete and service delete (T012)."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import VoucherRepository
from captive_portal.services.voucher_service import (
    VoucherNotFoundError,
    VoucherRedeemedError,
    VoucherService,
)


def _make_voucher(
    session,
    *,
    code="TESTCODE01",
    duration_minutes=60,
    status=VoucherStatus.UNUSED,
    redeemed_count=0,
    booking_ref=None,
):
    v = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
        booking_ref=booking_ref,
    )
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


class TestVoucherRepositoryDelete:
    def test_delete_unredeemed_returns_true(self, db_session: Session) -> None:
        _make_voucher(db_session, code="DELUNRED01", redeemed_count=0)
        repo = VoucherRepository(db_session)
        result = repo.delete("DELUNRED01")
        db_session.commit()
        assert result is True
        assert repo.get_by_code("DELUNRED01") is None

    def test_delete_redeemed_returns_false(self, db_session: Session) -> None:
        v = _make_voucher(db_session, code="DELREDMD01", redeemed_count=1)
        repo = VoucherRepository(db_session)
        result = repo.delete("DELREDMD01")
        assert result is False
        assert repo.get_by_code("DELREDMD01") is not None
        db_session.delete(v)
        db_session.commit()

    def test_delete_not_found_returns_false(self, db_session: Session) -> None:
        repo = VoucherRepository(db_session)
        assert repo.delete("NOTEXIST99") is False


class TestVoucherServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_unused_voucher(self, db_session: Session) -> None:
        _make_voucher(db_session, code="SVCDEL001", booking_ref="BK001")
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        meta = await service.delete("SVCDEL001")
        assert meta["status_at_delete"] == "unused"
        assert meta["booking_ref"] == "BK001"
        assert repo.get_by_code("SVCDEL001") is None

    @pytest.mark.asyncio
    async def test_delete_revoked_unredeemed_voucher(self, db_session: Session) -> None:
        _make_voucher(db_session, code="SVCDELRV1", status=VoucherStatus.REVOKED, redeemed_count=0)
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        meta = await service.delete("SVCDELRV1")
        assert meta["status_at_delete"] == "revoked"
        assert repo.get_by_code("SVCDELRV1") is None

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, db_session: Session) -> None:
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        with pytest.raises(VoucherNotFoundError):
            await service.delete("NOPE999999")

    @pytest.mark.asyncio
    async def test_delete_redeemed_raises(self, db_session: Session) -> None:
        v = _make_voucher(db_session, code="SVCDELRD1", redeemed_count=2)
        repo = VoucherRepository(db_session)
        service = VoucherService(session=db_session, voucher_repo=repo)
        with pytest.raises(VoucherRedeemedError):
            await service.delete("SVCDELRD1")
        db_session.delete(v)
        db_session.commit()
