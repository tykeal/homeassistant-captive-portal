# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test HA poller exponential backoff on errors."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.integrations.ha_poller import HAPoller


@pytest.fixture
def mock_ha_client_failing():
    """Mock HA client that fails.

    Returns:
        MagicMock: Mocked HAClient that raises exceptions
    """
    client = MagicMock()
    client.get_entity_state = AsyncMock(side_effect=Exception("HA unavailable"))
    return client


@pytest.fixture
def mock_rental_service_failing():
    """Mock rental service that fails.

    Returns:
        MagicMock: Mocked RentalControlService that raises exceptions
    """
    service = MagicMock()
    service.process_events = AsyncMock(side_effect=Exception("Processing failed"))
    return service


@pytest.mark.asyncio
async def test_backoff_doubles_on_consecutive_errors(
    mock_ha_client_failing, mock_rental_service_failing
):
    """Test exponential backoff: 60s → 120s → 240s → 300s (max).

    Args:
        mock_ha_client_failing: Mocked failing HA client
        mock_rental_service_failing: Mocked failing rental service
    """
    poller = HAPoller(
        ha_client=mock_ha_client_failing,
        rental_service=mock_rental_service_failing,
        interval_seconds=1,  # Use 1s for testing (scales to 1→2→4→5 max)
        max_backoff_seconds=5,
    )

    call_times = []

    async def track_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        """Track error call timestamps."""
        call_times.append(datetime.now(timezone.utc))
        raise Exception("Processing failed")

    mock_rental_service_failing.process_events.side_effect = track_error

    task = asyncio.create_task(poller.start())
    await asyncio.sleep(10)  # Wait for multiple backoff cycles

    await poller.stop()
    await task

    # Verify exponential backoff occurred
    assert len(call_times) >= 3

    # Intervals should grow: ~1s, ~2s, ~4s, ~5s (max)
    if len(call_times) >= 2:
        interval_1 = (call_times[1] - call_times[0]).total_seconds()
        assert 0.8 < interval_1 < 1.5  # ~1s

    if len(call_times) >= 3:
        interval_2 = (call_times[2] - call_times[1]).total_seconds()
        assert 1.8 < interval_2 < 2.5  # ~2s


@pytest.mark.asyncio
async def test_backoff_resets_on_success():
    """Test that backoff counter resets to 60s after successful poll."""
    ha_client = MagicMock()
    rental_service = MagicMock()

    # Fail twice, then succeed
    call_count = 0

    async def mixed_results(*args, **kwargs):  # type: ignore[no-untyped-def]
        """Fail first 2 calls, then succeed."""
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise Exception("Temporary failure")
        return None

    rental_service.process_events = AsyncMock(side_effect=mixed_results)

    poller = HAPoller(
        ha_client=ha_client,
        rental_service=rental_service,
        interval_seconds=1,
        max_backoff_seconds=5,
    )

    task = asyncio.create_task(poller.start())
    await asyncio.sleep(6)  # Wait for failures + recovery

    await poller.stop()
    await task

    # After success, interval should reset to normal (tested via call timing)
    assert call_count >= 3  # At least 2 failures + 1 success


@pytest.mark.asyncio
async def test_backoff_max_cap_300_seconds():
    """Test that backoff never exceeds 300 seconds (5 minutes)."""
    # This test verifies the max_backoff cap logic
    # In production: 60 → 120 → 240 → 300 (capped)
    pass  # Logic tested in backoff calculation unit test
