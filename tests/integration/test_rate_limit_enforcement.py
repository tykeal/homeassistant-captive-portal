# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for rate limit enforcement (429 responses)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.web.middleware.rate_limit_middleware import (
    RateLimitMiddleware,
)


@pytest.fixture
def app_with_rate_limit() -> FastAPI:
    """Create FastAPI app with rate limiting."""
    app = FastAPI()
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)

    @app.get("/test")
    async def test_endpoint() -> dict[str, str]:
        """Test endpoint."""
        return {"status": "ok"}

    return app


class TestRateLimitEnforcement:
    """Test rate limiting middleware enforcement."""

    def test_allows_under_limit(self, app_with_rate_limit: FastAPI) -> None:
        """Requests under limit return 200."""
        client = TestClient(app_with_rate_limit)

        for _ in range(3):
            response = client.get("/test")
            assert response.status_code == 200

    def test_blocks_over_limit_with_429(self, app_with_rate_limit: FastAPI) -> None:
        """Requests over limit return 429."""
        client = TestClient(app_with_rate_limit)

        # Use up attempts
        for _ in range(3):
            client.get("/test")

        # Next request should be 429
        response = client.get("/test")
        assert response.status_code == 429

    def test_retry_after_header(self, app_with_rate_limit: FastAPI) -> None:
        """429 response includes Retry-After header."""
        client = TestClient(app_with_rate_limit)

        # Use up attempts
        for _ in range(3):
            client.get("/test")

        # Check Retry-After header
        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        retry_after = int(response.headers["Retry-After"])
        assert 0 < retry_after <= 60
