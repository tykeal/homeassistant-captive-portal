# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for RentalControlService sensor discovery logging."""

import logging
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


@pytest.fixture
def integration_config() -> HAIntegrationConfig:
    """Create test integration config.

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
def mock_ha_client() -> MagicMock:
    """Create mock HA client.

    Returns:
        Mocked HAClient
    """
    client = MagicMock()
    client.get_entity_state = AsyncMock()
    return client


@pytest.fixture
def mock_event_repo() -> MagicMock:
    """Create mock event repository.

    Returns:
        Mocked event repository
    """
    repo = MagicMock()
    repo.upsert = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_warns_when_no_sensors_found(
    integration_config: HAIntegrationConfig,
    mock_ha_client: MagicMock,
    mock_event_repo: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log warning when no sensors match the integration prefix."""
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    all_states = [
        {"entity_id": "sensor.other_entity_0", "state": "active"},
        {"entity_id": "light.kitchen", "state": "on"},
    ]

    with caplog.at_level(logging.WARNING):
        await service._process_integration(integration_config, all_states)

    assert any("No event sensors found for integration" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_logs_info_when_sensors_found(
    integration_config: HAIntegrationConfig,
    mock_ha_client: MagicMock,
    mock_event_repo: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log info with sensor count when sensors are found."""
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    all_states = [
        {
            "entity_id": "sensor.rental_control_test_event_0",
            "state": "active",
            "attributes": {
                "start": "2025-10-26T10:00:00Z",
                "end": "2025-10-26T18:00:00Z",
                "slot_code": "12345",
                "slot_name": "Test Guest",
                "last_four": "5678",
            },
        },
        {
            "entity_id": "sensor.rental_control_test_event_1",
            "state": "No reservation",
            "attributes": {},
        },
    ]

    with caplog.at_level(logging.INFO):
        await service._process_integration(integration_config, all_states)

    assert any("Processed Rental Control events" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_no_warning_when_sensors_present(
    integration_config: HAIntegrationConfig,
    mock_ha_client: MagicMock,
    mock_event_repo: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No 'No event sensors' warning when sensors exist."""
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    all_states = [
        {
            "entity_id": "sensor.rental_control_test_event_0",
            "state": "active",
            "attributes": {
                "start": "2025-10-26T10:00:00Z",
                "end": "2025-10-26T18:00:00Z",
                "slot_code": "12345",
                "slot_name": "Test Guest",
                "last_four": "5678",
            },
        },
    ]

    with caplog.at_level(logging.WARNING):
        await service._process_integration(integration_config, all_states)

    assert not any("No event sensors found for integration" in r.message for r in caplog.records)
