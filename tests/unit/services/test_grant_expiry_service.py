# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for timer-driven grant expiry processing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.services.grant_expiry_service import GrantExpiryService


@pytest.mark.asyncio
async def test_process_once_marks_due_active_grants_expired(db_engine: Engine) -> None:
    """Due active grants are marked expired by the timer worker."""
    now = datetime.now(timezone.utc)
    with Session(db_engine) as session:
        grant = AccessGrant(
            device_id="AA:BB:CC:DD:EE:FF",
            mac="AA:BB:CC:DD:EE:FF",
            start_utc=now - timedelta(hours=2),
            end_utc=now - timedelta(minutes=1),
            status=GrantStatus.ACTIVE,
        )
        session.add(grant)
        session.commit()
        grant_id = grant.id

    service = GrantExpiryService(engine=db_engine, omada_config=None, interval_seconds=5)
    assert await service.process_once() == 1

    with Session(db_engine) as session:
        stored = session.get(AccessGrant, grant_id)
        assert stored is not None
        assert stored.status == GrantStatus.EXPIRED
