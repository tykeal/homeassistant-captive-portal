# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test Rental Control event processing and attribute selection."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from captive_portal.integrations.rental_control_service import RentalControlService
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr


@pytest.fixture
def integration_config_slot_code():
    """HAIntegrationConfig using slot_code.

    Returns:
        HAIntegrationConfig: Config with slot_code attribute
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="test_integration",
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=15,
    )


@pytest.fixture
def integration_config_slot_name():
    """HAIntegrationConfig using slot_name.

    Returns:
        HAIntegrationConfig: Config with slot_name attribute
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="test_integration",
        identifier_attr=IdentifierAttr.SLOT_NAME,
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
    repo.create = AsyncMock()
    repo.upsert = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_process_event_uses_slot_code_when_configured(
    integration_config_slot_code, mock_ha_client, mock_event_repo
):
    """Test that slot_code is used when configured.

    Args:
        integration_config_slot_code: Config with slot_code
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    event_data = {
        "attributes": {
            "start": "2025-10-26T10:00:00Z",
            "end": "2025-10-26T18:00:00Z",
            "slot_name": "John Doe",
            "slot_code": "12345",
            "last_four": "5678",
        }
    }

    await service.process_single_event(
        integration_config=integration_config_slot_code,
        event_index=0,
        event_data=event_data,
    )

    # Verify event was created with slot_code
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    assert call_args.slot_code == "12345"


@pytest.mark.asyncio
async def test_process_event_uses_slot_name_when_configured(
    integration_config_slot_name, mock_ha_client, mock_event_repo
):
    """Test that slot_name is used when configured.

    Args:
        integration_config_slot_name: Config with slot_name
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    event_data = {
        "attributes": {
            "start": "2025-10-26T10:00:00Z",
            "end": "2025-10-26T18:00:00Z",
            "slot_name": "John Doe",
            "slot_code": "12345",
            "last_four": "5678",
        }
    }

    await service.process_single_event(
        integration_config=integration_config_slot_name,
        event_index=0,
        event_data=event_data,
    )

    # Verify event was created with slot_name
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    assert call_args.slot_name == "John Doe"


@pytest.mark.asyncio
async def test_fallback_logic_slot_code_to_slot_name(
    integration_config_slot_code, mock_ha_client, mock_event_repo
):
    """Test fallback from slot_code to slot_name when slot_code is missing.

    Args:
        integration_config_slot_code: Config with slot_code
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    # Event missing slot_code
    event_data = {
        "attributes": {
            "start": "2025-10-26T10:00:00Z",
            "end": "2025-10-26T18:00:00Z",
            "slot_name": "John Doe",
            "last_four": "5678",
        }
    }

    await service.process_single_event(
        integration_config=integration_config_slot_code,
        event_index=0,
        event_data=event_data,
    )

    # Should fallback to slot_name
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    assert call_args.slot_name == "John Doe"


@pytest.mark.asyncio
async def test_skip_event_with_no_valid_identifier(
    integration_config_slot_code, mock_ha_client, mock_event_repo
):
    """Test that events with no valid identifiers are skipped.

    Args:
        integration_config_slot_code: Config with slot_code
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    # Event with no identifiers
    event_data = {
        "attributes": {
            "start": "2025-10-26T10:00:00Z",
            "end": "2025-10-26T18:00:00Z",
        }
    }

    await service.process_single_event(
        integration_config=integration_config_slot_code,
        event_index=0,
        event_data=event_data,
    )

    # Should not create event
    mock_event_repo.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_applies_grace_period_to_end_time(
    integration_config_slot_code, mock_ha_client, mock_event_repo
):
    """Test that event stores booking end without grace (applied at grant creation).

    Args:
        integration_config_slot_code: Config with 15 min grace
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    event_data = {
        "attributes": {
            "start": "2025-10-26T10:00:00Z",
            "end": "2025-10-26T18:00:00Z",
            "slot_code": "12345",
        }
    }

    await service.process_single_event(
        integration_config=integration_config_slot_code,
        event_index=0,
        event_data=event_data,
    )

    # Grace NOT applied here - event stores booking window (18:00)
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    expected_end = datetime(2025, 10, 26, 18, 0, tzinfo=timezone.utc)
    assert call_args.end_utc == expected_end
