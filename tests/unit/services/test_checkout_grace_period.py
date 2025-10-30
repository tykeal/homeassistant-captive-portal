# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for checkout grace period logic."""

from datetime import datetime, timedelta, timezone


from captive_portal.services.grant_service import calculate_grant_end_with_grace


class TestCheckoutGracePeriod:
    """Test grace period extension (0-30 min, grant expiry)."""

    def test_grace_period_extends_end(self) -> None:
        """Grace period extends booking end time."""
        booking_end = datetime.now(timezone.utc)
        grace_minutes = 15

        grant_end = calculate_grant_end_with_grace(booking_end, grace_minutes)

        expected = booking_end + timedelta(minutes=15)
        assert grant_end >= expected - timedelta(seconds=1)
        assert grant_end <= expected + timedelta(seconds=1)

    def test_zero_grace_period(self) -> None:
        """Zero grace period = no extension."""
        booking_end = datetime.now(timezone.utc)
        grace_minutes = 0

        grant_end = calculate_grant_end_with_grace(booking_end, grace_minutes)

        assert grant_end == booking_end

    def test_max_grace_period_30_minutes(self) -> None:
        """Maximum grace period is 30 minutes."""
        booking_end = datetime.now(timezone.utc)
        grace_minutes = 30

        grant_end = calculate_grant_end_with_grace(booking_end, grace_minutes)

        expected = booking_end + timedelta(minutes=30)
        assert grant_end >= expected - timedelta(seconds=1)
        assert grant_end <= expected + timedelta(seconds=1)

    def test_grace_period_validation(self) -> None:
        """Grace period must be 0-30 minutes."""
        booking_end = datetime.now(timezone.utc)

        # Valid values
        for minutes in [0, 15, 30]:
            result = calculate_grant_end_with_grace(booking_end, minutes)
            assert result is not None

        # Invalid values should be caught by model validation
        # (tested in model tests)
