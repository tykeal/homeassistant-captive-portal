# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for rate limiter (per-IP tracking, rolling window, cleanup)."""

from captive_portal.security.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test rate limiter functionality."""

    def test_allow_under_limit(self) -> None:
        """Requests under limit are allowed."""
        limiter = RateLimiter(max_attempts=5, window_seconds=60)
        ip = "192.168.1.1"

        for _ in range(5):
            assert limiter.is_allowed(ip) is True

    def test_block_over_limit(self) -> None:
        """Requests over limit are blocked."""
        limiter = RateLimiter(max_attempts=5, window_seconds=60)
        ip = "192.168.1.1"

        # Consume all attempts
        for _ in range(5):
            assert limiter.is_allowed(ip) is True

        # Next attempt should be blocked
        assert limiter.is_allowed(ip) is False

    def test_rolling_window(self) -> None:
        """Rate limiting uses rolling window."""
        limiter = RateLimiter(max_attempts=3, window_seconds=2)
        ip = "192.168.1.1"

        # Use all attempts
        for _ in range(3):
            assert limiter.is_allowed(ip) is True

        # Blocked immediately
        assert limiter.is_allowed(ip) is False

        # After window expires, should be allowed again
        import time

        time.sleep(2.1)
        assert limiter.is_allowed(ip) is True

    def test_per_ip_tracking(self) -> None:
        """Different IPs tracked independently."""
        limiter = RateLimiter(max_attempts=2, window_seconds=60)

        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"

        # IP1 uses up attempts
        assert limiter.is_allowed(ip1) is True
        assert limiter.is_allowed(ip1) is True
        assert limiter.is_allowed(ip1) is False  # blocked

        # IP2 still has attempts
        assert limiter.is_allowed(ip2) is True
        assert limiter.is_allowed(ip2) is True

    def test_cleanup_old_entries(self) -> None:
        """Cleanup removes entries older than window."""
        limiter = RateLimiter(max_attempts=5, window_seconds=1)
        ip = "192.168.1.1"

        # Add some attempts
        limiter.is_allowed(ip)
        limiter.is_allowed(ip)

        import time

        time.sleep(1.5)

        # Cleanup should remove old entries
        limiter.cleanup()

        # Should have fresh attempts after cleanup
        for _ in range(5):
            assert limiter.is_allowed(ip) is True

    def test_get_retry_after_seconds(self) -> None:
        """Get time until next attempt allowed."""
        limiter = RateLimiter(max_attempts=2, window_seconds=60)
        ip = "192.168.1.1"

        # Use up attempts
        limiter.is_allowed(ip)
        limiter.is_allowed(ip)

        retry_after = limiter.get_retry_after_seconds(ip)
        assert retry_after is not None
        assert 0 < retry_after <= 60

    def test_automatic_cleanup(self) -> None:
        """Automatic cleanup prevents memory leak."""
        from datetime import timedelta

        # Create limiter with short cleanup interval for testing
        limiter = RateLimiter(max_attempts=2, window_seconds=1)
        limiter._cleanup_interval_seconds = 2  # Override for testing

        # Simulate multiple IPs hitting rate limit
        for i in range(10):
            ip = f"192.168.1.{i}"
            limiter.is_allowed(ip)
            limiter.is_allowed(ip)

        # Verify entries exist
        assert len(limiter._attempts) == 10

        # Wait for entries to expire
        import time

        time.sleep(1.5)

        # Trigger automatic cleanup by making a new request
        # (after cleanup interval has passed)
        limiter._last_cleanup = limiter._last_cleanup - timedelta(
            seconds=limiter._cleanup_interval_seconds + 1
        )
        limiter.is_allowed("192.168.1.100")

        # All expired entries should be removed
        # Only the new IP should remain
        assert len(limiter._attempts) == 1
        assert "192.168.1.100" in limiter._attempts
