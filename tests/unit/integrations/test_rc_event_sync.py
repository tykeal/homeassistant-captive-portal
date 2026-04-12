# type: ignore
# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test Rental Control event syncing from HA sensors."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from captive_portal.integrations.rental_control_service import (
    RentalControlService,
)
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


# --- Fixtures ---------------------------------------------------------------


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
def second_integration_config():
    """Second HAIntegrationConfig for multi-integration tests.

    Returns:
        HAIntegrationConfig with a different calendar entity
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="calendar.rental_control_beach",
        identifier_attr=IdentifierAttr.SLOT_NAME,
        checkout_grace_minutes=10,
    )


def _make_sensor(entity_id, state, attrs):
    """Build an HA entity state dict for a sensor.

    Args:
        entity_id: Full entity ID string
        state: Entity state value
        attrs: Sensor attributes dict

    Returns:
        Dict matching HA REST API entity state format
    """
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attrs,
    }


def _booking_attrs(
    slot_code="12345",
    slot_name="John Doe",
    last_four="5678",
    start="2025-10-26T10:00:00+00:00",
    end="2025-10-28T10:00:00+00:00",
    summary="John Doe",
):
    """Build sensor attributes for a valid booking.

    Args:
        slot_code: Booking code
        slot_name: Guest name
        last_four: Last four phone digits
        start: Start ISO timestamp
        end: End ISO timestamp
        summary: Booking summary

    Returns:
        Attributes dict suitable for a sensor entity
    """
    return {
        "summary": summary,
        "start": start,
        "end": end,
        "slot_code": slot_code,
        "slot_name": slot_name,
        "last_four": last_four,
    }


def _make_service(
    ha_client=None,
    event_repo=None,
    configs=None,
):
    """Build a RentalControlService with mocks.

    Args:
        ha_client: Optional pre-built mock HAClient
        event_repo: Optional pre-built mock event repository
        configs: List of HAIntegrationConfig to return from DB

    Returns:
        Tuple of (service, mock_ha_client, mock_event_repo)
    """
    if ha_client is None:
        ha_client = MagicMock()
        ha_client.get_all_states = AsyncMock(return_value=[])

    if event_repo is None:
        event_repo = MagicMock()
        event_repo.upsert = AsyncMock()

    mock_session = MagicMock()
    if configs is None:
        configs = []
    mock_session.exec.return_value.all.return_value = configs
    event_repo.session = mock_session

    service = RentalControlService(
        ha_client=ha_client,
        event_repo=event_repo,
    )
    return service, ha_client, event_repo


# --- _derive_sensor_prefix tests -------------------------------------------


class TestDeriveSensorPrefix:
    """Tests for sensor entity ID derivation from calendar entity."""

    def test_standard_calendar_entity(self):
        """Standard calendar entity produces correct sensor prefix."""
        result = RentalControlService._derive_sensor_prefix(
            "calendar.rental_control_test",
        )
        assert result == "sensor.rental_control_test_event_"

    def test_multi_word_name(self):
        """Calendar entity with underscores in name works correctly."""
        result = RentalControlService._derive_sensor_prefix(
            "calendar.rental_control_beach_house",
        )
        assert result == "sensor.rental_control_beach_house_event_"

    def test_single_word_name(self):
        """Single word after rental_control_ works correctly."""
        result = RentalControlService._derive_sensor_prefix(
            "calendar.rental_control_cabin",
        )
        assert result == "sensor.rental_control_cabin_event_"

    def test_no_calendar_prefix(self):
        """Non-calendar entity ID is handled gracefully."""
        result = RentalControlService._derive_sensor_prefix(
            "sensor.rental_control_test",
        )
        assert result == "sensor.sensor.rental_control_test_event_"


# --- process_events tests ---------------------------------------------------


class TestProcessEvents:
    """Tests for the main process_events polling method."""

    @pytest.mark.asyncio
    async def test_no_configs_returns_early(self):
        """No integration configs means no HA API call."""
        service, mock_client, _ = _make_service(configs=[])

        await service.process_events()

        mock_client.get_all_states.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_states_once_for_multiple_configs(
        self,
        integration_config,
        second_integration_config,
    ):
        """All states fetched once regardless of config count."""
        service, mock_client, _ = _make_service(
            configs=[integration_config, second_integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[])

        await service.process_events()

        mock_client.get_all_states.assert_called_once()

    @pytest.mark.asyncio
    async def test_processes_matching_sensor(self, integration_config):
        """Sensor matching integration is processed via upsert."""
        sensor = _make_sensor(
            "sensor.rental_control_test_event_0",
            "John Doe",
            _booking_attrs(),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        mock_repo.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_processes_multiple_sensors(self, integration_config):
        """Multiple event sensors for same integration are all processed."""
        sensors = [
            _make_sensor(
                f"sensor.rental_control_test_event_{i}",
                f"Guest {i}",
                _booking_attrs(
                    slot_code=str(10000 + i),
                    slot_name=f"Guest {i}",
                    summary=f"Guest {i}",
                ),
            )
            for i in range(3)
        ]
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=sensors)

        await service.process_events()

        assert mock_repo.upsert.call_count == 3

    @pytest.mark.asyncio
    async def test_ignores_non_matching_sensors(self, integration_config):
        """Sensors not matching the integration prefix are ignored."""
        other_sensor = _make_sensor(
            "sensor.rental_control_beach_event_0",
            "Beach Guest",
            _booking_attrs(),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(
            return_value=[other_sensor],
        )

        await service.process_events()

        mock_repo.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_last_sync_on_success(self, integration_config):
        """Successful sync updates last_sync_utc and resets stale_count."""
        integration_config.stale_count = 5
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[])

        before = datetime.now(timezone.utc)
        await service.process_events()

        assert integration_config.last_sync_utc is not None
        assert integration_config.last_sync_utc >= before
        assert integration_config.stale_count == 0

    @pytest.mark.asyncio
    async def test_commits_session_after_processing(self, integration_config):
        """Session is committed after all integrations are processed."""
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[])

        await service.process_events()

        mock_repo.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_index_extracted_from_entity_id(
        self,
        integration_config,
    ):
        """Event index is parsed from the sensor entity ID suffix."""
        sensor = _make_sensor(
            "sensor.rental_control_test_event_3",
            "Guest Three",
            _booking_attrs(),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        call_args = mock_repo.upsert.call_args[0][0]
        assert call_args.event_index == 3

    @pytest.mark.asyncio
    async def test_invalid_event_index_skipped(self, integration_config):
        """Sensor with non-numeric event index suffix is skipped."""
        sensor = _make_sensor(
            "sensor.rental_control_test_event_abc",
            "Guest",
            _booking_attrs(),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        mock_repo.upsert.assert_not_called()


# --- Filtering "No reservation" sensors ------------------------------------


class TestNoReservationFiltering:
    """Tests for skipping sensors without valid bookings."""

    @pytest.mark.asyncio
    async def test_skips_no_reservation_state(self, integration_config):
        """Sensor with state 'No reservation' is skipped."""
        sensor = _make_sensor(
            "sensor.rental_control_test_event_0",
            "No reservation",
            _booking_attrs(),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        mock_repo.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_unavailable_state(self, integration_config):
        """Sensor with state 'unavailable' is skipped."""
        sensor = _make_sensor(
            "sensor.rental_control_test_event_0",
            "unavailable",
            _booking_attrs(),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        mock_repo.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_no_reservation_in_summary(self, integration_config):
        """Sensor with 'No reservation' in summary attribute is skipped."""
        sensor = _make_sensor(
            "sensor.rental_control_test_event_0",
            "some_state",
            _booking_attrs(summary="No reservation found"),
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        mock_repo.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_processes_valid_sensor_alongside_skipped(
        self,
        integration_config,
    ):
        """Valid sensor is processed even when others are skipped."""
        sensors = [
            _make_sensor(
                "sensor.rental_control_test_event_0",
                "No reservation",
                _booking_attrs(),
            ),
            _make_sensor(
                "sensor.rental_control_test_event_1",
                "John Doe",
                _booking_attrs(),
            ),
        ]
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=sensors)

        await service.process_events()

        mock_repo.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_string_summary_not_filtered(self, integration_config):
        """Non-string summary attribute does not cause a skip."""
        attrs = _booking_attrs()
        attrs["summary"] = 42
        sensor = _make_sensor(
            "sensor.rental_control_test_event_0",
            "active",
            attrs,
        )
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=[sensor])

        await service.process_events()

        mock_repo.upsert.assert_called_once()


# --- Error isolation --------------------------------------------------------


class TestProcessEventsErrorIsolation:
    """Tests for per-integration error isolation."""

    @pytest.mark.asyncio
    async def test_one_failing_integration_does_not_block_others(
        self,
        integration_config,
        second_integration_config,
    ):
        """Error in one integration does not prevent processing others."""
        sensors = [
            _make_sensor(
                "sensor.rental_control_test_event_0",
                "Guest A",
                _booking_attrs(
                    slot_code=None,
                    slot_name=None,
                    last_four=None,
                    summary="Guest A",
                ),
            ),
            _make_sensor(
                "sensor.rental_control_beach_event_0",
                "Guest B",
                _booking_attrs(summary="Guest B"),
            ),
        ]
        service, mock_client, mock_repo = _make_service(
            configs=[integration_config, second_integration_config],
        )
        mock_client.get_all_states = AsyncMock(return_value=sensors)

        await service.process_events()

        # Second integration should still be synced
        assert second_integration_config.stale_count == 0
        assert second_integration_config.last_sync_utc is not None
        mock_repo.session.commit.assert_called_once()
