# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test grace period logic for voucher extension."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from captive_portal.integrations.rental_control_service import RentalControlService
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr


@pytest.fixture
def integration_15min_grace():
    """HAIntegrationConfig with 15-minute grace period.

    Returns:
        HAIntegrationConfig: Config with 15 min grace
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="test",
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=15,
    )


@pytest.fixture
def integration_0min_grace():
    """HAIntegrationConfig with 0-minute grace period (disabled).

    Returns:
        HAIntegrationConfig: Config with 0 min grace
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="test",
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=0,
    )


@pytest.fixture
def integration_30min_grace():
    """HAIntegrationConfig with 30-minute grace period (maximum).

    Returns:
        HAIntegrationConfig: Config with 30 min grace
    """
    return HAIntegrationConfig(
        id=uuid4(),
        integration_id="test",
        identifier_attr=IdentifierAttr.SLOT_CODE,
        checkout_grace_minutes=30,
    )


@pytest.fixture
def mock_event_repo():
    """Mock event repository.

    Returns:
        MagicMock: Mocked event repository
    """
    repo = MagicMock()
    repo.upsert = AsyncMock()
    return repo


@pytest.fixture
def mock_ha_client():
    """Mock HA client.

    Returns:
        MagicMock: Mocked HA client
    """
    client = MagicMock()
    client.get_entity_state = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_15_minute_grace_extends_end_time(
    integration_15min_grace, mock_ha_client, mock_event_repo
):
    """Test that event stores booking window without grace (applied at grant time).

    Args:
        integration_15min_grace: Config with 15 min grace
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    checkout_time = datetime(2025, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    event_data = {
        "attributes": {
            "start": "2025-10-26T08:00:00Z",
            "end": checkout_time.isoformat(),
            "slot_code": "12345",
        }
    }

    await service.process_single_event(
        integration_config=integration_15min_grace,
        event_index=0,
        event_data=event_data,
    )

    # Grace period NOT applied here - stored booking window is checkout_time
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    assert call_args.end_utc == checkout_time


@pytest.mark.asyncio
async def test_0_minute_grace_no_extension(integration_0min_grace, mock_ha_client, mock_event_repo):
    """Test that 0-minute grace period does not extend end time.

    Args:
        integration_0min_grace: Config with 0 min grace
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    checkout_time = datetime(2025, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    event_data = {
        "attributes": {
            "start": "2025-10-26T08:00:00Z",
            "end": checkout_time.isoformat(),
            "slot_code": "12345",
        }
    }

    await service.process_single_event(
        integration_config=integration_0min_grace,
        event_index=0,
        event_data=event_data,
    )

    # No grace period
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    assert call_args.end_utc == checkout_time


@pytest.mark.asyncio
async def test_30_minute_grace_max_extension(
    integration_30min_grace, mock_ha_client, mock_event_repo
):
    """Test that event stores booking window without grace (max 30 min applied at grant time).

    Args:
        integration_30min_grace: Config with 30 min grace
        mock_ha_client: Mocked HA client
        mock_event_repo: Mocked event repository
    """
    service = RentalControlService(ha_client=mock_ha_client, event_repo=mock_event_repo)

    checkout_time = datetime(2025, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    event_data = {
        "attributes": {
            "start": "2025-10-26T08:00:00Z",
            "end": checkout_time.isoformat(),
            "slot_code": "12345",
        }
    }

    await service.process_single_event(
        integration_config=integration_30min_grace,
        event_index=0,
        event_data=event_data,
    )

    # Grace period NOT applied here - stored booking window is checkout_time
    mock_event_repo.upsert.assert_called_once()
    call_args = mock_event_repo.upsert.call_args[0][0]
    assert call_args.end_utc == checkout_time


def test_grace_period_validation_rejects_over_30() -> None:
    """Test that grace period validation rejects values over 30 minutes."""
    with pytest.raises(ValueError):
        HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=31,  # Over max
        )


def test_grace_period_validation_rejects_negative() -> None:
    """Test that grace period validation rejects negative values."""
    with pytest.raises(ValueError):
        HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=-1,  # Negative
        )
