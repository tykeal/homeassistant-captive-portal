# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for AccessGrantRepository active grant counting methods.

Covers count_active_by_voucher_code() and count_active_by_voucher_codes()
for the multi-device voucher feature.
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import AccessGrantRepository


def _make_voucher(session: Session, *, code: str, max_devices: int = 1) -> Voucher:
    """Create and persist a voucher for testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=60,
        status=VoucherStatus.UNUSED,
        max_devices=max_devices,
    )
    session.add(voucher)
    session.commit()
    session.refresh(voucher)
    return voucher


def _make_grant(
    session: Session,
    *,
    voucher_code: str,
    mac: str,
    status: GrantStatus = GrantStatus.ACTIVE,
) -> AccessGrant:
    """Create and persist an access grant for testing."""
    now = datetime.now(timezone.utc)
    grant = AccessGrant(
        voucher_code=voucher_code,
        mac=mac,
        device_id=mac,
        start_utc=now,
        end_utc=now + timedelta(hours=1),
        status=status,
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


class TestCountActiveByVoucherCode:
    """Tests for AccessGrantRepository.count_active_by_voucher_code()."""

    def test_zero_grants_returns_zero(self, db_session: Session) -> None:
        """Voucher with no grants should return count of 0."""
        _make_voucher(db_session, code="COUNTZERO1")
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTZERO1") == 0

    def test_active_grants_counted(self, db_session: Session) -> None:
        """Active grants should be included in the count."""
        _make_voucher(db_session, code="COUNTACT1", max_devices=5)
        _make_grant(db_session, voucher_code="COUNTACT1", mac="AA:BB:CC:DD:EE:01")
        _make_grant(db_session, voucher_code="COUNTACT1", mac="AA:BB:CC:DD:EE:02")
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTACT1") == 2

    def test_pending_grants_counted(self, db_session: Session) -> None:
        """Pending grants should be included in the count."""
        _make_voucher(db_session, code="COUNTPND1", max_devices=5)
        _make_grant(
            db_session,
            voucher_code="COUNTPND1",
            mac="AA:BB:CC:DD:EE:01",
            status=GrantStatus.PENDING,
        )
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTPND1") == 1

    def test_revoked_grants_excluded(self, db_session: Session) -> None:
        """Revoked grants should NOT be counted (frees slot per FR-007)."""
        _make_voucher(db_session, code="COUNTREV1", max_devices=5)
        _make_grant(
            db_session,
            voucher_code="COUNTREV1",
            mac="AA:BB:CC:DD:EE:01",
            status=GrantStatus.REVOKED,
        )
        _make_grant(db_session, voucher_code="COUNTREV1", mac="AA:BB:CC:DD:EE:02")
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTREV1") == 1

    def test_failed_grants_excluded(self, db_session: Session) -> None:
        """Failed grants should NOT be counted."""
        _make_voucher(db_session, code="COUNTFAL1", max_devices=5)
        _make_grant(
            db_session,
            voucher_code="COUNTFAL1",
            mac="AA:BB:CC:DD:EE:01",
            status=GrantStatus.FAILED,
        )
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTFAL1") == 0

    def test_expired_grants_excluded(self, db_session: Session) -> None:
        """Expired grants should NOT be counted."""
        _make_voucher(db_session, code="COUNTEXP1", max_devices=5)
        _make_grant(
            db_session,
            voucher_code="COUNTEXP1",
            mac="AA:BB:CC:DD:EE:01",
            status=GrantStatus.EXPIRED,
        )
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTEXP1") == 0

    def test_mixed_statuses_only_active_pending_counted(self, db_session: Session) -> None:
        """Only pending and active statuses should contribute to count."""
        _make_voucher(db_session, code="COUNTMIX1", max_devices=10)
        _make_grant(db_session, voucher_code="COUNTMIX1", mac="AA:BB:CC:DD:EE:01")
        _make_grant(
            db_session,
            voucher_code="COUNTMIX1",
            mac="AA:BB:CC:DD:EE:02",
            status=GrantStatus.PENDING,
        )
        _make_grant(
            db_session,
            voucher_code="COUNTMIX1",
            mac="AA:BB:CC:DD:EE:03",
            status=GrantStatus.REVOKED,
        )
        _make_grant(
            db_session,
            voucher_code="COUNTMIX1",
            mac="AA:BB:CC:DD:EE:04",
            status=GrantStatus.FAILED,
        )
        _make_grant(
            db_session,
            voucher_code="COUNTMIX1",
            mac="AA:BB:CC:DD:EE:05",
            status=GrantStatus.EXPIRED,
        )
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_code("COUNTMIX1") == 2


class TestCountActiveByVoucherCodes:
    """Tests for AccessGrantRepository.count_active_by_voucher_codes()."""

    def test_empty_input_returns_empty_dict(self, db_session: Session) -> None:
        """Empty code list should return empty dict."""
        repo = AccessGrantRepository(db_session)
        assert repo.count_active_by_voucher_codes([]) == {}

    def test_multiple_codes_with_varying_counts(self, db_session: Session) -> None:
        """Batch query returns correct counts for multiple voucher codes."""
        _make_voucher(db_session, code="BATCHCNT1", max_devices=5)
        _make_voucher(db_session, code="BATCHCNT2", max_devices=5)
        _make_grant(db_session, voucher_code="BATCHCNT1", mac="AA:BB:CC:DD:EE:01")
        _make_grant(db_session, voucher_code="BATCHCNT1", mac="AA:BB:CC:DD:EE:02")
        _make_grant(db_session, voucher_code="BATCHCNT2", mac="AA:BB:CC:DD:EE:03")
        repo = AccessGrantRepository(db_session)
        result = repo.count_active_by_voucher_codes(["BATCHCNT1", "BATCHCNT2"])
        assert result == {"BATCHCNT1": 2, "BATCHCNT2": 1}

    def test_codes_with_zero_grants_excluded(self, db_session: Session) -> None:
        """Codes with no active grants should not appear in result."""
        _make_voucher(db_session, code="BATCHZR1", max_devices=5)
        _make_voucher(db_session, code="BATCHZR2", max_devices=5)
        _make_grant(db_session, voucher_code="BATCHZR1", mac="AA:BB:CC:DD:EE:01")
        repo = AccessGrantRepository(db_session)
        result = repo.count_active_by_voucher_codes(["BATCHZR1", "BATCHZR2"])
        assert result == {"BATCHZR1": 1}
        assert "BATCHZR2" not in result
