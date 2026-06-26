# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for timer-driven grant expiry processing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.services.grant_expiry_service import GrantExpiryService


class FailingAdapter:
    """Adapter double that fails controller revocation."""

    async def revoke(
        self,
        mac: str,
        grant_id: str | None = None,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        vid: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
    ) -> dict[str, Any]:
        """Raise a controller error for revoke attempts."""
        raise OmadaClientError("controller unavailable")

    async def authorize(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        """Return unused authorize response."""
        return {}

    async def update(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        """Return unused update response."""
        return {}

    async def get_status(self, _mac: str) -> dict[str, Any]:
        """Return unused status response."""
        return {}


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


@pytest.mark.asyncio
async def test_process_once_keeps_grant_active_when_revoke_fails(
    db_engine: Engine,
) -> None:
    """Failed controller revocation leaves a due grant retryable."""
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

    def build_adapter() -> OmadaControllerAdapter:
        """Return a failing adapter double."""
        return FailingAdapter()

    service._build_adapter = build_adapter  # type: ignore[method-assign]

    assert await service.process_once() == 0

    with Session(db_engine) as session:
        stored = session.get(AccessGrant, grant_id)
        assert stored is not None
        assert stored.status == GrantStatus.ACTIVE
