# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for timer-driven grant expiry processing."""

from __future__ import annotations

import asyncio
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


@pytest.mark.asyncio
async def test_worker_logs_unexpected_errors_and_continues(
    db_engine: Engine,
) -> None:
    """Unexpected process errors do not terminate the expiry worker."""
    service = GrantExpiryService(engine=db_engine, omada_config=None, interval_seconds=0.01)
    calls = 0

    async def process_once() -> int:
        """Raise once, then stop the worker on the next iteration."""
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database unavailable")
        await service.stop()
        return 0

    service.process_once = process_once  # type: ignore[method-assign]

    await asyncio.wait_for(service.start(), timeout=1)

    assert calls == 2


@pytest.mark.asyncio
async def test_process_once_builds_adapter_once_for_batch(db_engine: Engine) -> None:
    """A batch of due grants reuses one adapter for the iteration."""
    now = datetime.now(timezone.utc)
    with Session(db_engine) as session:
        for index in range(2):
            session.add(
                AccessGrant(
                    device_id=f"AA:BB:CC:DD:EE:F{index}",
                    mac=f"AA:BB:CC:DD:EE:F{index}",
                    start_utc=now - timedelta(hours=2),
                    end_utc=now - timedelta(minutes=1),
                    status=GrantStatus.ACTIVE,
                )
            )
        session.commit()

    service = GrantExpiryService(engine=db_engine, omada_config=None, interval_seconds=5)
    build_calls = 0

    def build_adapter() -> None:
        """Count adapter construction calls."""
        nonlocal build_calls
        build_calls += 1
        return None

    service._build_adapter = build_adapter  # type: ignore[method-assign]

    assert await service.process_once() == 2
    assert build_calls == 1


@pytest.mark.asyncio
async def test_process_once_skips_adapter_when_no_grants(db_engine: Engine) -> None:
    """No adapter is built when no grants are due."""
    service = GrantExpiryService(engine=db_engine, omada_config=None, interval_seconds=5)
    build_calls = 0

    def build_adapter() -> None:
        """Track unexpected adapter construction."""
        nonlocal build_calls
        build_calls += 1
        return None

    service._build_adapter = build_adapter  # type: ignore[method-assign]

    assert await service.process_once() == 0
    assert build_calls == 0
