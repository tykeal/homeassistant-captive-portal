# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for VoucherRepository purge methods and AccessGrantRepository nullify.

T009: count_purgeable, get_purgeable_codes, purge
T010: nullify_voucher_references
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)


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


class TestVoucherRepositoryPurge:
    """T009: Tests for purge repository methods."""

    def test_count_purgeable_returns_correct_count(self, db_session: Session) -> None:
        """Count only EXPIRED/REVOKED vouchers past cutoff."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        old_time = cutoff - timedelta(days=10)

        _make_voucher(
            db_session, code="PRGTST0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )
        _make_voucher(
            db_session, code="PRGTST0002", status=VoucherStatus.REVOKED, status_changed_utc=old_time
        )
        # Within retention
        _make_voucher(
            db_session,
            code="PRGTST0003",
            status=VoucherStatus.EXPIRED,
            status_changed_utc=datetime.now(timezone.utc),
        )
        # Non-terminal
        _make_voucher(
            db_session, code="PRGTST0004", status=VoucherStatus.UNUSED, status_changed_utc=None
        )
        _make_voucher(
            db_session, code="PRGTST0005", status=VoucherStatus.ACTIVE, status_changed_utc=None
        )

        repo = VoucherRepository(db_session)
        count = repo.count_purgeable(cutoff)
        assert count == 2

    def test_get_purgeable_codes_returns_correct_codes(self, db_session: Session) -> None:
        """Get codes of EXPIRED/REVOKED vouchers past cutoff."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        old_time = cutoff - timedelta(days=5)

        _make_voucher(
            db_session, code="PRGCODE001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )
        _make_voucher(
            db_session, code="PRGCODE002", status=VoucherStatus.REVOKED, status_changed_utc=old_time
        )
        _make_voucher(
            db_session,
            code="PRGCODE003",
            status=VoucherStatus.EXPIRED,
            status_changed_utc=datetime.now(timezone.utc),
        )

        repo = VoucherRepository(db_session)
        codes = repo.get_purgeable_codes(cutoff)
        assert set(codes) == {"PRGCODE001", "PRGCODE002"}

    def test_purge_deletes_correct_vouchers(self, db_session: Session) -> None:
        """Purge deletes only eligible vouchers and returns count."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        old_time = cutoff - timedelta(days=10)

        _make_voucher(
            db_session, code="PRGDEL0001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )
        _make_voucher(
            db_session, code="PRGDEL0002", status=VoucherStatus.REVOKED, status_changed_utc=old_time
        )
        _make_voucher(
            db_session,
            code="PRGDEL0003",
            status=VoucherStatus.EXPIRED,
            status_changed_utc=datetime.now(timezone.utc),
        )
        _make_voucher(db_session, code="PRGDEL0004", status=VoucherStatus.UNUSED)

        repo = VoucherRepository(db_session)
        deleted = repo.purge(cutoff)
        db_session.commit()

        assert deleted == 2
        # Verify they're gone
        assert repo.get_by_code("PRGDEL0001") is None
        assert repo.get_by_code("PRGDEL0002") is None
        # These should remain
        assert repo.get_by_code("PRGDEL0003") is not None
        assert repo.get_by_code("PRGDEL0004") is not None

    def test_purge_preserves_active_unused(self, db_session: Session) -> None:
        """ACTIVE and UNUSED vouchers are never purged regardless of age."""
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc)

        _make_voucher(db_session, code="PRGSAFE001", status=VoucherStatus.UNUSED)
        _make_voucher(
            db_session, code="PRGSAFE002", status=VoucherStatus.ACTIVE, activated_utc=old_time
        )

        repo = VoucherRepository(db_session)
        deleted = repo.purge(cutoff)
        assert deleted == 0

    def test_purge_zero_result_case(self, db_session: Session) -> None:
        """Purge with no eligible vouchers returns 0."""
        repo = VoucherRepository(db_session)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        deleted = repo.purge(cutoff)
        assert deleted == 0

    def test_purge_idempotent_rerun(self, db_session: Session) -> None:
        """Running purge twice does not cause errors."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        old_time = cutoff - timedelta(days=10)

        _make_voucher(
            db_session, code="PRGIDMP001", status=VoucherStatus.EXPIRED, status_changed_utc=old_time
        )

        repo = VoucherRepository(db_session)
        first_run = repo.purge(cutoff)
        db_session.commit()
        assert first_run == 1

        second_run = repo.purge(cutoff)
        db_session.commit()
        assert second_run == 0


class TestAccessGrantRepositoryNullify:
    """T010: Tests for nullify_voucher_references."""

    def test_nullifies_matching_grants(self, db_session: Session) -> None:
        """Sets voucher_code to NULL for matching grants."""
        _make_voucher(db_session, code="NULLTST001", status=VoucherStatus.EXPIRED)
        grant = _make_grant(db_session, voucher_code="NULLTST001")

        repo = AccessGrantRepository(db_session)
        updated = repo.nullify_voucher_references(["NULLTST001"])
        db_session.commit()

        assert updated == 1
        db_session.refresh(grant)
        assert grant.voucher_code is None

    def test_preserves_unrelated_grants(self, db_session: Session) -> None:
        """Grants with different voucher codes are not affected."""
        _make_voucher(db_session, code="NULLPRS001", status=VoucherStatus.EXPIRED)
        _make_voucher(db_session, code="NULLPRS002", status=VoucherStatus.ACTIVE)
        _make_grant(db_session, voucher_code="NULLPRS001", mac="AA:BB:CC:DD:EE:01")
        grant2 = _make_grant(db_session, voucher_code="NULLPRS002", mac="AA:BB:CC:DD:EE:02")

        repo = AccessGrantRepository(db_session)
        repo.nullify_voucher_references(["NULLPRS001"])
        db_session.commit()

        db_session.refresh(grant2)
        assert grant2.voucher_code == "NULLPRS002"

    def test_handles_empty_list(self, db_session: Session) -> None:
        """Empty list input returns 0 without error."""
        repo = AccessGrantRepository(db_session)
        result = repo.nullify_voucher_references([])
        assert result == 0

    def test_returns_count_of_updated_grants(self, db_session: Session) -> None:
        """Returns correct count of updated grants."""
        _make_voucher(db_session, code="NULLCNT001", status=VoucherStatus.EXPIRED)
        _make_grant(db_session, voucher_code="NULLCNT001", mac="AA:BB:CC:DD:EE:01")
        _make_grant(db_session, voucher_code="NULLCNT001", mac="AA:BB:CC:DD:EE:02")

        repo = AccessGrantRepository(db_session)
        count = repo.nullify_voucher_references(["NULLCNT001"])
        assert count == 2
