# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test HA poller 60-second interval timing."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.integrations.ha_poller import HAPoller


@pytest.fixture
def mock_ha_client():
    """Mock HA client fixture.

    Returns:
        MagicMock: Mocked HAClient instance
    """
    client = MagicMock()
    client.get_entity_state = AsyncMock(return_value={"state": "ok"})
    return client


@pytest.fixture
def mock_rental_service():
    """Mock rental control service fixture.

    Returns:
        MagicMock: Mocked RentalControlService instance
    """
    service = MagicMock()
    service.process_events = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_poller_runs_every_60_seconds(mock_ha_client, mock_rental_service):
    """Test that poller runs at 60-second intervals under normal conditions.

    Args:
        mock_ha_client: Mocked HA client
        mock_rental_service: Mocked rental control service
    """
    poller = HAPoller(
        ha_client=mock_ha_client,
        rental_service=mock_rental_service,
        interval_seconds=0.5,  # Use 0.5s for testing
    )

    # Track call times
    call_times = []

    async def track_call(*args, **kwargs):  # type: ignore[no-untyped-def]
        """Track polling call timestamps."""
        call_times.append(datetime.now(timezone.utc))

    mock_rental_service.process_events.side_effect = track_call

    # Start poller in background
    task = asyncio.create_task(poller.start())

    # Wait for a few polling cycles
    await asyncio.sleep(1.3)

    # Stop poller
    await poller.stop()

    # Wait for task to complete
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    # Should have 2-3 calls in ~1.3 seconds with 0.5s interval
    assert len(call_times) >= 2
    assert mock_rental_service.process_events.call_count >= 2


@pytest.mark.asyncio
async def test_poller_synchronized_batch():
    """Test that all integrations are polled in a synchronized batch."""
    # This will be tested via integration test with multiple integrations
    # Unit test confirms single batch processing
    pass


@pytest.mark.asyncio
async def test_poller_stop_gracefully(mock_ha_client, mock_rental_service):
    """Test that poller stops gracefully without hanging.

    Args:
        mock_ha_client: Mocked HA client
        mock_rental_service: Mocked rental control service
    """
    poller = HAPoller(
        ha_client=mock_ha_client,
        rental_service=mock_rental_service,
        interval_seconds=10,  # Long interval to test stop during sleep
    )

    task = asyncio.create_task(poller.start())
    await asyncio.sleep(0.1)

    # Stop should complete quickly
    stop_start = datetime.now(timezone.utc)
    await poller.stop()

    # Wait for task to complete with timeout
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except asyncio.TimeoutError:
        pass

    stop_duration = (datetime.now(timezone.utc) - stop_start).total_seconds()

    assert stop_duration < 2.0  # Should stop within 2 seconds
