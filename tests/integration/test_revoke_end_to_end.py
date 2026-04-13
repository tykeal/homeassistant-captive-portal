# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for end-to-end revoke flow (admin revoke -> controller removal)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.persistence.repositories import AccessGrantRepository
from captive_portal.services.grant_service import GrantNotFoundError, GrantService


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
        controller_grant_id="ctrl_123",
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


class TestRevokeEndToEnd:
    """Test complete revoke flow from admin action to status update."""

    @pytest.mark.asyncio
    async def test_admin_revoke_grant_updates_status(self, db_session: Session) -> None:
        """Revoking grant should update status to REVOKED."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:01")
        assert grant.status == GrantStatus.ACTIVE

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)

        assert result.status == GrantStatus.REVOKED
        assert result.updated_utc is not None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_grant_raises(self, db_session: Session) -> None:
        """Revoking nonexistent grant raises GrantNotFoundError."""
        from uuid import uuid4

        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        with pytest.raises(GrantNotFoundError):
            await svc.revoke(uuid4())

    @pytest.mark.asyncio
    async def test_revoke_already_expired_grant_transitions(self, db_session: Session) -> None:
        """Revoking expired grant should set status to REVOKED."""
        grant = _make_grant(
            db_session,
            mac="AA:BB:CC:DD:EE:03",
            status=GrantStatus.EXPIRED,
        )
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_pending_grant_prevents_activation(self, db_session: Session) -> None:
        """Revoking PENDING grant sets status to REVOKED."""
        grant = _make_grant(
            db_session,
            mac="AA:BB:CC:DD:EE:04",
            status=GrantStatus.PENDING,
        )
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_is_idempotent(self, db_session: Session) -> None:
        """Revoking an already-revoked grant is idempotent."""
        grant = _make_grant(
            db_session,
            mac="AA:BB:CC:DD:EE:05",
            status=GrantStatus.REVOKED,
        )
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        result = await svc.revoke(grant.id)
        assert result.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_persists_across_refresh(self, db_session: Session) -> None:
        """Revoked status persists when re-fetched from database."""
        grant = _make_grant(db_session, mac="AA:BB:CC:DD:EE:06")
        repo = AccessGrantRepository(db_session)
        svc = GrantService(session=db_session, grant_repo=repo)
        await svc.revoke(grant.id)

        fetched = repo.get_by_id(grant.id)
        assert fetched is not None
        assert fetched.status == GrantStatus.REVOKED
