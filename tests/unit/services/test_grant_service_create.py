# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test grant service creation logic."""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import GrantStatus
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.services.grant_service import GrantService


class TestGrantServiceCreate:
    """Test GrantService.create() method."""

    @pytest.mark.asyncio
    async def test_create_grant_with_voucher_code(self, db_session: Session) -> None:
        """Create grant with voucher_code FK sets reference correctly."""
        voucher = Voucher(code="TESTCODE01", duration_minutes=60, status=VoucherStatus.UNUSED)
        db_session.add(voucher)
        db_session.commit()

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        grant = await svc.create(
            mac="AA:BB:CC:DD:EE:01",
            start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
            voucher_code="TESTCODE01",
        )
        assert grant.voucher_code == "TESTCODE01"

    @pytest.mark.asyncio
    async def test_create_grant_with_booking_ref(self, db_session: Session) -> None:
        """Create grant with booking_ref (nullable, case-sensitive)."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        grant = await svc.create(
            mac="AA:BB:CC:DD:EE:02",
            start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
            booking_ref="BookRef_2025_Test",
        )
        assert grant.booking_ref == "BookRef_2025_Test"

    @pytest.mark.asyncio
    async def test_create_grant_requires_mac(self, db_session: Session) -> None:
        """Create grant requires MAC address (non-null)."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        with pytest.raises(ValueError, match="MAC address is required"):
            await svc.create(
                mac="",
                start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
                end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_create_grant_rounds_timestamps_to_minute(self, db_session: Session) -> None:
        """Create grant floors start_utc, ceils end_utc to minute precision."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        start = datetime(2025, 1, 1, 12, 0, 45, 123456, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 13, 5, 15, 654321, tzinfo=timezone.utc)

        grant = await svc.create(mac="AA:BB:CC:DD:EE:03", start_utc=start, end_utc=end)

        assert grant.start_utc.second == 0
        assert grant.start_utc.microsecond == 0
        # SQLite strips tzinfo; compare naive values
        assert grant.start_utc.replace(tzinfo=None) == datetime(2025, 1, 1, 12, 0)
        assert grant.end_utc.second == 0
        assert grant.end_utc.microsecond == 0
        assert grant.end_utc.replace(tzinfo=None) == datetime(2025, 1, 1, 13, 6)

    @pytest.mark.asyncio
    async def test_create_grant_default_status_pending(self, db_session: Session) -> None:
        """Create grant defaults to status=PENDING until controller confirms."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        grant = await svc.create(
            mac="AA:BB:CC:DD:EE:04",
            start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
        )
        assert grant.status == GrantStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_grant_generates_uuid(self, db_session: Session) -> None:
        """Create grant generates UUID for primary key."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        grant = await svc.create(
            mac="AA:BB:CC:DD:EE:05",
            start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
        )
        assert isinstance(grant.id, UUID)

    @pytest.mark.asyncio
    async def test_create_grant_persists_to_repository(self, db_session: Session) -> None:
        """Create commits grant to AccessGrantRepository."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        grant = await svc.create(
            mac="AA:BB:CC:DD:EE:06",
            start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
        )
        fetched = repo.get_by_id(grant.id)
        assert fetched is not None
        assert fetched.mac == "AA:BB:CC:DD:EE:06"

    @pytest.mark.asyncio
    async def test_create_grant_with_session_token_fallback(self, db_session: Session) -> None:
        """Create grant with session_token when voucher_code is null."""
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        grant = await svc.create(
            mac="AA:BB:CC:DD:EE:07",
            start_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            end_utc=datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
            session_token="SESSION_TOKEN_ABC",
        )
        assert grant.session_token == "SESSION_TOKEN_ABC"
        assert grant.voucher_code is None
