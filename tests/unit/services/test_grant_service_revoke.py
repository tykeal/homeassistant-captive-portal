# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test grant revocation logic (US2: Admin manages access grants)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.services.grant_service import GrantService


def _make_grant(
    session: Session,
    *,
    mac: str = "AA:BB:CC:DD:EE:01",
    status: GrantStatus = GrantStatus.ACTIVE,
) -> AccessGrant:
    """Create and persist a grant for testing."""
    base = datetime.now(timezone.utc)
    grant = AccessGrant(
        device_id=mac,
        mac=mac,
        start_utc=base - timedelta(hours=1),
        end_utc=base + timedelta(hours=1),
        status=status,
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


class TestGrantServiceRevoke:
    """Test GrantService.revoke() method."""

    @pytest.mark.asyncio
    async def test_revoke_active_grant_transitions_to_revoked(self, db_session: Session) -> None:
        """Revoke active grant transitions status ACTIVE -> REVOKED."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:01")
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_pending_grant_transitions_to_revoked(self, db_session: Session) -> None:
        """Revoke pending grant transitions status PENDING -> REVOKED."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:02", status=GrantStatus.PENDING)
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_expired_grant_idempotent(self, db_session: Session) -> None:
        """Revoke expired grant (already past end_utc) is no-op but succeeds."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:03", status=GrantStatus.EXPIRED)
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_idempotent(self, db_session: Session) -> None:
        """Revoke already-revoked grant is idempotent (no error)."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:04", status=GrantStatus.REVOKED)
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_updates_updated_utc(self, db_session: Session) -> None:
        """Revoke sets grant.updated_utc to current timestamp."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:05")
        now = datetime.now(timezone.utc)

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id, current_time=now)
        # SQLite strips tzinfo; compare naive values
        assert result.updated_utc.replace(tzinfo=None) == now.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_revoke_persists_changes(self, db_session: Session) -> None:
        """Revoke commits updated grant to repository."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:06")
        grant_id = grant.id

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        await svc.revoke(grant_id)

        fetched = repo.get_by_id(grant_id)
        assert fetched is not None
        assert fetched.status == GrantStatus.REVOKED
