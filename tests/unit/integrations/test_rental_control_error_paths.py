# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Focused Rental Control service edge-path tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.integrations.rental_control_service import RentalControlService
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr
from captive_portal.models.rental_control_event import RentalControlEvent


def _service() -> tuple[RentalControlService, MagicMock]:
    """Build a service with mocked HA client and event repository."""
    repo = MagicMock()
    repo.upsert = AsyncMock()
    repo.delete_events_older_than = AsyncMock(return_value=0)
    repo.session = MagicMock()
    return RentalControlService(ha_client=MagicMock(), event_repo=repo), repo


def _config(identifier_attr: IdentifierAttr = IdentifierAttr.SLOT_CODE) -> HAIntegrationConfig:
    """Build an HA integration config for edge-path tests."""
    return HAIntegrationConfig(
        integration_id="calendar.rental_control_guest",
        identifier_attr=identifier_attr,
    )


def _event(
    *,
    slot_name: str | None = None,
    slot_code: str | None = None,
    last_four: str | None = None,
) -> RentalControlEvent:
    """Build a Rental Control event with configurable identifiers."""
    now = datetime.now(timezone.utc)
    return RentalControlEvent(
        integration_id="calendar.rental_control_guest",
        event_index=0,
        slot_name=slot_name,
        slot_code=slot_code,
        last_four=last_four,
        start_utc=now,
        end_utc=now,
        raw_attributes="{}",
    )


@pytest.mark.asyncio
async def test_purge_stale_events_rolls_back_and_reraises() -> None:
    """Cleanup failures roll back the repository session and propagate."""
    service, repo = _service()
    repo.delete_events_older_than = AsyncMock(side_effect=RuntimeError("database down"))

    with pytest.raises(RuntimeError, match="database down"):
        await service._purge_stale_events()

    repo.session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_process_single_event_skips_missing_timestamps() -> None:
    """Events missing start or end timestamps are skipped safely."""
    service, repo = _service()

    await service.process_single_event(
        integration_config=_config(),
        event_index=2,
        event_data={"attributes": {"start": "2026-01-01T00:00:00Z", "slot_code": "1234"}},
    )

    repo.upsert.assert_not_called()


def test_get_auth_identifier_prefers_configured_and_fallback_values() -> None:
    """Identifier selection uses configured values before documented fallbacks."""
    service, _repo = _service()

    assert (
        service.get_auth_identifier(
            _event(slot_code="1234", slot_name="Guest"),
            _config(IdentifierAttr.SLOT_CODE),
        )
        == "1234"
    )
    assert (
        service.get_auth_identifier(
            _event(slot_code="1234", slot_name="Guest"),
            _config(IdentifierAttr.LAST_FOUR),
        )
        == "1234"
    )
    assert (
        service.get_auth_identifier(
            _event(slot_name="Guest"),
            _config(IdentifierAttr.LAST_FOUR),
        )
        == "Guest"
    )
    assert service.get_auth_identifier(_event(), _config(IdentifierAttr.LAST_FOUR)) is None
