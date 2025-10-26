# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Time utility functions for timestamp rounding and manipulation."""

from datetime import datetime, timedelta, timezone


def floor_to_minute(dt: datetime) -> datetime:
    """Floor datetime to minute precision (remove seconds/microseconds).

    Args:
        dt: Datetime to floor

    Returns:
        Datetime with seconds and microseconds set to 0
    """
    return dt.replace(second=0, microsecond=0)


def ceil_to_minute(dt: datetime) -> datetime:
    """Ceil datetime to next minute if not already on minute boundary.

    Args:
        dt: Datetime to ceil

    Returns:
        Datetime rounded up to next minute if seconds/microseconds > 0,
        otherwise unchanged
    """
    if dt.second > 0 or dt.microsecond > 0:
        return dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return dt


def utc_now() -> datetime:
    """Get current UTC datetime.

    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(timezone.utc)
