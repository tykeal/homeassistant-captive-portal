# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin-configurable rate limiting."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.web.middleware.rate_limit_middleware import (
    RateLimitMiddleware,
)


class TestRateLimitConfigurable:
    """Test admin-configurable rate limit parameters."""

    def test_custom_attempts_limit(self) -> None:
        """Admin can configure max attempts."""
        app = FastAPI()
        limiter = RateLimiter(max_attempts=10, window_seconds=60)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            """Test endpoint."""
            return {"status": "ok"}

        client = TestClient(app)

        # Should allow 10 attempts
        for _ in range(10):
            response = client.get("/test")
            assert response.status_code == 200

        # 11th should be blocked
        response = client.get("/test")
        assert response.status_code == 429

    def test_custom_window_duration(self) -> None:
        """Admin can configure time window."""
        app = FastAPI()
        # Short window for testing
        limiter = RateLimiter(max_attempts=2, window_seconds=1)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            """Test endpoint."""
            return {"status": "ok"}

        client = TestClient(app)

        # Use up attempts
        client.get("/test")
        client.get("/test")

        # Should be blocked
        response = client.get("/test")
        assert response.status_code == 429

        # After window, should be allowed
        import time

        time.sleep(1.5)

        response = client.get("/test")
        assert response.status_code == 200
