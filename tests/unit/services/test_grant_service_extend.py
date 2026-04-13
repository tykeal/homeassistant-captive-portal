# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test grant extension logic (US2: Admin manages access grants)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.services.grant_service import (
    GrantOperationError,
    GrantService,
)


def _make_grant(
    session: Session,
    *,
    mac: str = "AA:BB:CC:DD:EE:01",
    status: GrantStatus = GrantStatus.ACTIVE,
    end_utc: datetime | None = None,
) -> AccessGrant:
    """Create and persist a grant for testing."""
    base = datetime.now(timezone.utc)
    grant = AccessGrant(
        device_id=mac,
        mac=mac,
        start_utc=base - timedelta(hours=1),
        end_utc=end_utc or (base + timedelta(hours=1)),
        status=status,
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


class TestGrantServiceExtend:
    """Test GrantService.extend() method."""

    @pytest.mark.asyncio
    async def test_extend_grant_increases_end_utc(self, db_session: Session) -> None:
        """Extend grant adds minutes to end_utc (ceiled to minute precision)."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:01")
        original_end = grant.end_utc

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.extend(grant.id, additional_minutes=60)

        expected = original_end + timedelta(minutes=60)
        assert result.end_utc >= expected
        assert result.end_utc.second == 0
        assert result.end_utc.microsecond == 0

    @pytest.mark.asyncio
    async def test_extend_grant_updates_updated_utc(self, db_session: Session) -> None:
        """Extend updates grant.updated_utc to current timestamp."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:02")
        now = datetime.now(timezone.utc)

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.extend(grant.id, additional_minutes=30, current_time=now)
        # SQLite strips tzinfo; compare naive values
        assert result.updated_utc.replace(tzinfo=None) == now.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_extend_grant_persists_changes(self, db_session: Session) -> None:
        """Extend commits updated grant to repository."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:03")
        original_end = grant.end_utc

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        await svc.extend(grant.id, additional_minutes=60)

        fetched = repo.get_by_id(grant.id)
        assert fetched is not None
        assert fetched.end_utc > original_end

    @pytest.mark.asyncio
    async def test_extend_expired_grant_reactivates(self, db_session: Session) -> None:
        """Extend expired grant transitions status EXPIRED -> ACTIVE."""
        grant = _make_grant(
            db_session,
            mac="AA:BB:CC:DD:EE:04",
            status=GrantStatus.EXPIRED,
        )
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.extend(grant.id, additional_minutes=60)
        assert result.status == GrantStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_extend_revoked_grant_fails(self, db_session: Session) -> None:
        """Extend revoked grant raises exception (cannot revive revoked)."""
        grant = _make_grant(
            db_session,
            mac="AA:BB:CC:DD:EE:05",
            status=GrantStatus.REVOKED,
        )
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        with pytest.raises(GrantOperationError):
            await svc.extend(grant.id, additional_minutes=60)
