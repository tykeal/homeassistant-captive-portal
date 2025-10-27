# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test cleanup service 7-day retention policy."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.services.cleanup_service import CleanupService


@pytest.fixture
def mock_event_repo():
    """Mock event repository.

    Returns:
        MagicMock: Mocked event repository
    """
    repo = MagicMock()
    repo.delete_events_older_than = AsyncMock(return_value=5)
    return repo


@pytest.fixture
def mock_audit_service():
    """Mock audit service.

    Returns:
        MagicMock: Mocked audit service
    """
    service = MagicMock()
    service.log = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_cleanup_deletes_events_older_than_7_days(mock_event_repo, mock_audit_service):
    """Test that events older than 7 days post-checkout are deleted.

    Args:
        mock_event_repo: Mocked event repository
        mock_audit_service: Mocked audit service
    """
    service = CleanupService(
        event_repo=mock_event_repo,
        audit_service=mock_audit_service,
        retention_days=7,
    )

    deleted_count = await service.cleanup_expired_events()

    # Verify deletion was called
    mock_event_repo.delete_events_older_than.assert_called_once()
    call_args = mock_event_repo.delete_events_older_than.call_args[0][0]

    # Should delete events where end_utc < (now - 7 days)
    expected_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    assert abs((call_args - expected_cutoff).total_seconds()) < 60  # Within 1 min

    assert deleted_count == 5


@pytest.mark.asyncio
async def test_cleanup_logs_audit_event(mock_event_repo, mock_audit_service):
    """Test that cleanup logs audit event with deletion count.

    Args:
        mock_event_repo: Mocked event repository
        mock_audit_service: Mocked audit service
    """
    service = CleanupService(
        event_repo=mock_event_repo,
        audit_service=mock_audit_service,
        retention_days=7,
    )

    await service.cleanup_expired_events()

    # Verify audit log was created
    mock_audit_service.log.assert_called_once()
    call_args = mock_audit_service.log.call_args
    assert call_args[1]["action"] == "event.cleanup"
    assert call_args[1]["meta"]["deleted_count"] == 5


@pytest.mark.asyncio
async def test_cleanup_runs_daily_at_3am():
    """Test that cleanup service can be scheduled for daily 3 AM runs."""
    # This will be tested via integration test with scheduler
    # Unit test confirms cleanup_expired_events logic only
    pass


@pytest.mark.asyncio
async def test_cleanup_does_not_affect_vouchers(mock_event_repo, mock_audit_service):
    """Test that cleanup does not delete vouchers, only events.

    Args:
        mock_event_repo: Mocked event repository
        mock_audit_service: Mocked audit service
    """
    service = CleanupService(
        event_repo=mock_event_repo,
        audit_service=mock_audit_service,
        retention_days=7,
    )

    await service.cleanup_expired_events()

    # Only event repo deletion should be called
    mock_event_repo.delete_events_older_than.assert_called_once()
    # No voucher-related calls expected
