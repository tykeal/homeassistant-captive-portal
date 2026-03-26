# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T005 – Integration tests for admin cache-control headers (FR-028).

Verifies that Cache-Control, Pragma, and Expires headers are present on
all ``/admin/*`` responses to prevent back-button content leakage after
logout, and that non-admin paths are unaffected.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def secure_client(db_engine: Any) -> TestClient:
    """Client backed by a real create_app() with SecurityHeadersMiddleware.

    Uses db_engine fixture to ensure the database is initialized before
    the application starts.
    """
    from captive_portal.app import create_app

    test_app = create_app()
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminCacheHeaders:
    """SecurityHeadersMiddleware must inject cache-control headers on /admin/* responses."""

    def test_admin_login_cache_control(self, secure_client: TestClient) -> None:
        """GET /admin/login must include Cache-Control: no-store, no-cache, must-revalidate."""
        resp = secure_client.get("/admin/login")
        assert resp.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"

    def test_admin_login_pragma(self, secure_client: TestClient) -> None:
        """GET /admin/login must include Pragma: no-cache."""
        resp = secure_client.get("/admin/login")
        assert resp.headers["Pragma"] == "no-cache"

    def test_admin_login_expires(self, secure_client: TestClient) -> None:
        """GET /admin/login must include Expires: 0."""
        resp = secure_client.get("/admin/login")
        assert resp.headers["Expires"] == "0"

    def test_non_admin_path_no_cache_control(self, secure_client: TestClient) -> None:
        """Non-admin paths must NOT include the no-store Cache-Control directive."""
        resp = secure_client.get("/api/health")
        cache_control = resp.headers.get("Cache-Control", "")
        assert "no-store" not in cache_control

    def test_auth_required_admin_path_has_cache_headers(self, secure_client: TestClient) -> None:
        """An admin path that requires auth must still carry all three cache headers.

        /admin/portal-settings/ requires authentication and returns 401 for
        unauthenticated requests.  The security-headers middleware must still
        inject the cache-control headers on the error response.
        """
        resp = secure_client.get("/admin/portal-settings/", follow_redirects=False)
        # Regardless of status code, cache headers must be present
        assert resp.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
        assert resp.headers["Pragma"] == "no-cache"
        assert resp.headers["Expires"] == "0"
