# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for VoucherPurgeService.

T011: auto_purge, count_purgeable, manual_purge with audit logging,
grant nullification, and zero-result handling.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_purge_service import VoucherPurgeService


def _make_voucher(
    session: Session,
    *,
    code: str,
    status: VoucherStatus = VoucherStatus.EXPIRED,
    duration_minutes: int = 60,
    status_changed_utc: datetime | None = None,
    activated_utc: datetime | None = None,
) -> Voucher:
    """Create and persist a voucher for testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        activated_utc=activated_utc,
        status_changed_utc=status_changed_utc,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return voucher


def _make_grant(
    session: Session,
    *,
    voucher_code: str | None = None,
    mac: str = "AA:BB:CC:DD:EE:01",
) -> AccessGrant:
    """Create and persist a grant for testing."""
    now = datetime.now(timezone.utc)
    grant = AccessGrant(
        voucher_code=voucher_code,
        mac=mac,
        device_id=mac,
        start_utc=now,
        end_utc=now + timedelta(hours=1),
        status=GrantStatus.ACTIVE,
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


def _make_purge_service(session: Session, retention_days: int = 30) -> VoucherPurgeService:
    """Create a VoucherPurgeService with real repositories."""
    return VoucherPurgeService(
        voucher_repo=VoucherRepository(session),
        grant_repo=AccessGrantRepository(session),
        audit_service=AuditService(session),
        retention_days=retention_days,
    )


class TestVoucherPurgeServiceAutoPurge:
    """T011: auto_purge() tests."""

    @pytest.mark.asyncio
    async def test_auto_purge_uses_30_day_retention(self, db_session: Session) -> None:
        """Auto-purge uses default 30-day retention cutoff."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _make_voucher(
            db_session, code="AUTPRG0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        service = _make_purge_service(db_session)
        count = await service.auto_purge()

        assert count == 1
        repo = VoucherRepository(db_session)
        assert repo.get_by_code("AUTPRG0001") is None

    @pytest.mark.asyncio
    async def test_auto_purge_nullifies_grants_before_delete(self, db_session: Session) -> None:
        """Auto-purge nullifies grant references before deleting vouchers."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _make_voucher(
            db_session, code="AUTNUL0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )
        grant = _make_grant(db_session, voucher_code="AUTNUL0001")

        service = _make_purge_service(db_session)
        count = await service.auto_purge()

        assert count == 1
        db_session.refresh(grant)
        assert grant.voucher_code is None

    @pytest.mark.asyncio
    async def test_auto_purge_creates_audit_entry(self, db_session: Session) -> None:
        """Auto-purge creates audit entry with correct action and metadata."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _make_voucher(
            db_session, code="AUTAUD0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        service = _make_purge_service(db_session)
        await service.auto_purge()

        # Find the audit entry
        from typing import Any

        stmt: Any = select(AuditLog).where(AuditLog.action == "voucher.auto_purge")
        entries = list(db_session.exec(stmt).all())
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor == "system"
        assert entry.outcome == "success"
        assert entry.target_type == "voucher"
        assert entry.meta["purged_count"] == 1
        assert entry.meta["retention_days"] == 30
        assert "cutoff_utc" in entry.meta

    @pytest.mark.asyncio
    async def test_auto_purge_skips_audit_when_zero_purged(self, db_session: Session) -> None:
        """No audit entry when zero vouchers are purged."""
        service = _make_purge_service(db_session)
        count = await service.auto_purge()

        assert count == 0
        from typing import Any

        stmt: Any = select(AuditLog).where(AuditLog.action == "voucher.auto_purge")
        entries = list(db_session.exec(stmt).all())
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_auto_purge_concurrent_safe(self, db_session: Session) -> None:
        """Double-purge does not cause errors."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _make_voucher(
            db_session, code="AUTCON0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        service = _make_purge_service(db_session)
        first = await service.auto_purge()
        second = await service.auto_purge()

        assert first == 1
        assert second == 0


class TestVoucherPurgeServiceCountPurgeable:
    """Tests for count_purgeable()."""

    @pytest.mark.asyncio
    async def test_count_with_age_threshold(self, db_session: Session) -> None:
        """Count only vouchers older than min_age_days."""
        old_time = datetime.now(timezone.utc) - timedelta(days=15)
        very_old = datetime.now(timezone.utc) - timedelta(days=45)

        _make_voucher(
            db_session, code="CNTAGE0001", status=VoucherStatus.EXPIRED, status_changed_utc=very_old
        )
        _make_voucher(
            db_session, code="CNTAGE0002", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        service = _make_purge_service(db_session)
        count = await service.count_purgeable(30)
        assert count == 1

    @pytest.mark.asyncio
    async def test_count_zero_means_all_terminal(self, db_session: Session) -> None:
        """N=0 counts all terminal vouchers regardless of age."""
        _make_voucher(
            db_session,
            code="CNTZRO0001",
            status=VoucherStatus.EXPIRED,
            status_changed_utc=datetime.now(timezone.utc),
        )
        _make_voucher(
            db_session,
            code="CNTZRO0002",
            status=VoucherStatus.REVOKED,
            status_changed_utc=datetime.now(timezone.utc),
        )
        _make_voucher(db_session, code="CNTZRO0003", status=VoucherStatus.UNUSED)

        service = _make_purge_service(db_session)
        count = await service.count_purgeable(0)
        assert count == 2


class TestVoucherPurgeServiceManualPurge:
    """Tests for manual_purge()."""

    @pytest.mark.asyncio
    async def test_manual_purge_with_age_threshold(self, db_session: Session) -> None:
        """Manual purge with N=14 deletes vouchers older than 14 days."""
        old_time = datetime.now(timezone.utc) - timedelta(days=15)
        _make_voucher(
            db_session, code="MANPRG0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        service = _make_purge_service(db_session)
        count = await service.manual_purge(14, actor="admin_user")

        assert count == 1
        repo = VoucherRepository(db_session)
        assert repo.get_by_code("MANPRG0001") is None

    @pytest.mark.asyncio
    async def test_manual_purge_audit_entry(self, db_session: Session) -> None:
        """Manual purge creates audit entry with admin actor."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _make_voucher(
            db_session, code="MANAUD0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        service = _make_purge_service(db_session)
        await service.manual_purge(30, actor="admin_user")

        from typing import Any

        stmt: Any = select(AuditLog).where(AuditLog.action == "voucher.manual_purge")
        entries = list(db_session.exec(stmt).all())
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor == "admin_user"
        assert entry.meta["purged_count"] == 1
        assert entry.meta["min_age_days"] == 30

    @pytest.mark.asyncio
    async def test_manual_purge_zero_all_terminal(self, db_session: Session) -> None:
        """N=0 purges all terminal vouchers."""
        _make_voucher(
            db_session,
            code="MANZRO0001",
            status=VoucherStatus.EXPIRED,
            status_changed_utc=datetime.now(timezone.utc),
        )

        service = _make_purge_service(db_session)
        count = await service.manual_purge(0, actor="admin")
        assert count == 1
