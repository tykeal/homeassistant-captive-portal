# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Rate limiter for preventing brute-force attacks."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone


class RateLimiter:
    """
    Per-IP rate limiter with rolling window.

    Tracks authorization attempts per IP address and enforces configurable
    rate limits to prevent brute-force attacks.

    Attributes:
        max_attempts: Maximum attempts allowed within window
        window_seconds: Time window in seconds for rate limiting
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60) -> None:
        """
        Initialize rate limiter.

        Args:
            max_attempts: Maximum attempts per window (default: 5)
            window_seconds: Window duration in seconds (default: 60)
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[datetime]] = defaultdict(list)

    def is_allowed(self, ip_address: str) -> bool:
        """
        Check if request from IP is allowed.

        Args:
            ip_address: Client IP address

        Returns:
            True if allowed, False if rate limited
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.window_seconds)

        # Clean old attempts
        self._attempts[ip_address] = [ts for ts in self._attempts[ip_address] if ts > window_start]

        # Check if under limit
        if len(self._attempts[ip_address]) < self.max_attempts:
            self._attempts[ip_address].append(now)
            return True

        return False

    def get_retry_after_seconds(self, ip_address: str) -> int | None:
        """
        Get seconds until next attempt allowed for IP.

        Args:
            ip_address: Client IP address

        Returns:
            Seconds to wait, or None if allowed now
        """
        if not self._attempts[ip_address]:
            return None

        now = datetime.now(timezone.utc)
        oldest_attempt = min(self._attempts[ip_address])
        retry_at = oldest_attempt + timedelta(seconds=self.window_seconds)

        if retry_at <= now:
            return None

        return int((retry_at - now).total_seconds()) + 1

    def cleanup(self) -> None:
        """Remove expired entries to free memory."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.window_seconds)

        for ip in list(self._attempts.keys()):
            self._attempts[ip] = [ts for ts in self._attempts[ip] if ts > window_start]
            if not self._attempts[ip]:
                del self._attempts[ip]
