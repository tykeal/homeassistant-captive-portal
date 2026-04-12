# type: ignore
# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test timezone conversion for Rental Control event timestamps."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from captive_portal.integrations.rental_control_service import RentalControlService
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


@pytest.fixture
def integration_config():
    """HAIntegrationConfig using slot_code.

    Returns:
        HAIntegrationConfig with slot_code identifier
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="calendar.rental_control_test",
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=15,
    )


@pytest.fixture
def mock_ha_client():
    """Mock HA client.

    Returns:
        MagicMock: Mocked HAClient
    """
    client = MagicMock()
    client.get_entity_state = AsyncMock()
    return client


@pytest.fixture
def mock_event_repo():
    """Mock event repository.

    Returns:
        MagicMock: Mocked event repository
    """
    repo = MagicMock()
    repo.upsert = AsyncMock()
    return repo


def _event_data(start: str, end: str, slot_code: str = "12345"):
    """Build minimal event data dict.

    Args:
        start: ISO start timestamp string
        end: ISO end timestamp string
        slot_code: Booking slot code

    Returns:
        Event data dict with attributes
    """
    return {
        "attributes": {
            "start": start,
            "end": end,
            "slot_code": slot_code,
        }
    }


class TestTimezoneAwareConversion:
    """Aware datetime strings are converted to UTC."""

    @pytest.mark.asyncio
    async def test_pdt_offset_converted_to_utc(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """PDT offset (UTC-7) is converted to UTC correctly."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        data = _event_data(
            start="2026-04-12T10:00:00-07:00",
            end="2026-04-12T13:00:00-07:00",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
        )

        mock_event_repo.upsert.assert_called_once()
        event = mock_event_repo.upsert.call_args[0][0]
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            4,
            12,
            20,
            0,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_positive_offset_converted_to_utc(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """Positive UTC offset (e.g. CET +01:00) is converted correctly."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        data = _event_data(
            start="2026-01-15T14:00:00+01:00",
            end="2026-01-15T16:00:00+01:00",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
        )

        event = mock_event_repo.upsert.call_args[0][0]
        assert event.start_utc == datetime(
            2026,
            1,
            15,
            13,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            1,
            15,
            15,
            0,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_utc_z_suffix_stays_utc(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """Z-suffixed timestamps remain UTC after conversion."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        data = _event_data(
            start="2026-04-12T17:00:00Z",
            end="2026-04-12T20:00:00Z",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
        )

        event = mock_event_repo.upsert.call_args[0][0]
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            4,
            12,
            20,
            0,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_explicit_utc_offset_stays_utc(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """Explicit +00:00 offset stays UTC."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        data = _event_data(
            start="2026-04-12T17:00:00+00:00",
            end="2026-04-12T20:00:00+00:00",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
        )

        event = mock_event_repo.upsert.call_args[0][0]
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            4,
            12,
            20,
            0,
            tzinfo=timezone.utc,
        )


class TestNaiveDatetimeConversion:
    """Naive datetime strings are interpreted using HA timezone."""

    @pytest.mark.asyncio
    async def test_naive_with_ha_tz_converts_correctly(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """Naive datetime uses ha_tz to produce correct UTC."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        ha_tz = ZoneInfo("America/Los_Angeles")
        data = _event_data(
            start="2026-04-12T10:00:00",
            end="2026-04-12T13:00:00",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
            ha_tz=ha_tz,
        )

        event = mock_event_repo.upsert.call_args[0][0]
        # April in LA is PDT (UTC-7)
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            4,
            12,
            20,
            0,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_naive_defaults_to_utc_when_no_ha_tz(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """Naive datetime defaults to UTC when ha_tz is None."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        data = _event_data(
            start="2026-04-12T17:00:00",
            end="2026-04-12T20:00:00",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
        )

        event = mock_event_repo.upsert.call_args[0][0]
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            4,
            12,
            20,
            0,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_naive_with_eastern_tz(
        self,
        integration_config,
        mock_ha_client,
        mock_event_repo,
    ):
        """Naive datetime with US/Eastern timezone (EDT, UTC-4)."""
        service = RentalControlService(
            ha_client=mock_ha_client,
            event_repo=mock_event_repo,
        )
        ha_tz = ZoneInfo("America/New_York")
        data = _event_data(
            start="2026-06-15T09:00:00",
            end="2026-06-15T12:00:00",
        )

        await service.process_single_event(
            integration_config=integration_config,
            event_index=0,
            event_data=data,
            ha_tz=ha_tz,
        )

        event = mock_event_repo.upsert.call_args[0][0]
        # June in NYC is EDT (UTC-4)
        assert event.start_utc == datetime(
            2026,
            6,
            15,
            13,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            6,
            15,
            16,
            0,
            tzinfo=timezone.utc,
        )


class TestProcessEventsTimezoneIntegration:
    """process_events fetches HA timezone and passes it down."""

    @pytest.mark.asyncio
    async def test_process_events_calls_get_timezone(
        self,
        integration_config,
    ):
        """process_events fetches HA timezone once per poll cycle."""
        mock_client = MagicMock()
        mock_client.get_all_states = AsyncMock(return_value=[])
        mock_client.get_timezone = AsyncMock(return_value="UTC")

        mock_repo = MagicMock()
        mock_repo.upsert = AsyncMock()
        mock_session = MagicMock()
        mock_session.exec.return_value.all.return_value = [
            integration_config,
        ]
        mock_repo.session = mock_session

        service = RentalControlService(
            ha_client=mock_client,
            event_repo=mock_repo,
        )

        await service.process_events()

        mock_client.get_timezone.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_events_passes_ha_tz_to_process_single(
        self,
        integration_config,
    ):
        """HA timezone is forwarded to process_single_event."""
        sensor = {
            "entity_id": "sensor.rental_control_test_event_0",
            "state": "Jane Doe",
            "attributes": {
                "start": "2026-04-12T10:00:00",
                "end": "2026-04-12T13:00:00",
                "slot_code": "99999",
                "summary": "Jane Doe",
            },
        }
        mock_client = MagicMock()
        mock_client.get_all_states = AsyncMock(
            return_value=[sensor],
        )
        mock_client.get_timezone = AsyncMock(
            return_value="America/Los_Angeles",
        )

        mock_repo = MagicMock()
        mock_repo.upsert = AsyncMock()
        mock_session = MagicMock()
        mock_session.exec.return_value.all.return_value = [
            integration_config,
        ]
        mock_repo.session = mock_session

        service = RentalControlService(
            ha_client=mock_client,
            event_repo=mock_repo,
        )

        await service.process_events()

        event = mock_repo.upsert.call_args[0][0]
        # Naive 10:00 PDT (UTC-7) should become 17:00 UTC
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
        assert event.end_utc == datetime(
            2026,
            4,
            12,
            20,
            0,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_process_events_invalid_tz_falls_back_to_utc(
        self,
        integration_config,
    ):
        """Invalid HA timezone falls back to UTC without aborting."""
        sensor = {
            "entity_id": "sensor.rental_control_test_event_0",
            "state": "Guest",
            "attributes": {
                "start": "2026-04-12T17:00:00Z",
                "end": "2026-04-12T20:00:00Z",
                "slot_code": "11111",
                "summary": "Guest",
            },
        }
        mock_client = MagicMock()
        mock_client.get_all_states = AsyncMock(
            return_value=[sensor],
        )
        mock_client.get_timezone = AsyncMock(
            return_value="Invalid/Timezone",
        )

        mock_repo = MagicMock()
        mock_repo.upsert = AsyncMock()
        mock_session = MagicMock()
        mock_session.exec.return_value.all.return_value = [
            integration_config,
        ]
        mock_repo.session = mock_session

        service = RentalControlService(
            ha_client=mock_client,
            event_repo=mock_repo,
        )

        await service.process_events()

        # Should still process despite invalid tz
        mock_repo.upsert.assert_called_once()
        event = mock_repo.upsert.call_args[0][0]
        assert event.start_utc == datetime(
            2026,
            4,
            12,
            17,
            0,
            tzinfo=timezone.utc,
        )
