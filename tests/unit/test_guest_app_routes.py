# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests verifying all admin routes return 404 on guest app."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


@pytest.fixture
def guest_app() -> FastAPI:
    """Create guest app for admin route isolation testing."""
    return create_guest_app(settings=AppSettings(db_path=":memory:"))


@pytest.fixture
def guest_client(guest_app: FastAPI) -> TestClient:
    """Create test client for the guest app (no lifespan needed for 404 checks)."""
    return TestClient(guest_app, raise_server_exceptions=False)


# All admin routes that MUST return 404 on the guest app
ADMIN_GET_ROUTES = [
    "/admin/portal-settings/",
    "/admin/docs",
    "/admin/redoc",
    "/admin/integrations",
    "/api/admin/auth/login",
    "/api/admin/accounts",
    "/api/grants",
    "/api/grants/",
    "/api/vouchers",
    "/api/portal/config",
    "/api/audit/config",
    "/api/integrations",
    "/grants",
]

ADMIN_POST_ROUTES = [
    "/api/admin/auth/login",
    "/api/vouchers",
]

ADMIN_PUT_ROUTES = [
    "/api/portal/config",
]


class TestAdminRoutesReturn404OnGuest:
    """Verify all admin routes return 404 Not Found on guest listener."""

    @pytest.mark.parametrize("path", ADMIN_GET_ROUTES)
    def test_admin_get_route_returns_404(self, guest_client: TestClient, path: str) -> None:
        """Admin GET route returns 404 (not 401/403) on guest app."""
        response = guest_client.get(path)
        assert response.status_code == 404, (
            f"Expected 404 for GET {path}, got {response.status_code}"
        )

    @pytest.mark.parametrize("path", ADMIN_POST_ROUTES)
    def test_admin_post_route_returns_404(self, guest_client: TestClient, path: str) -> None:
        """Admin POST route returns 404 (not 401/403) on guest app."""
        response = guest_client.post(path, json={})
        assert response.status_code == 404, (
            f"Expected 404 for POST {path}, got {response.status_code}"
        )

    @pytest.mark.parametrize("path", ADMIN_PUT_ROUTES)
    def test_admin_put_route_returns_404(self, guest_client: TestClient, path: str) -> None:
        """Admin PUT route returns 404 (not 401/403) on guest app."""
        response = guest_client.put(path, json={})
        assert response.status_code == 404, (
            f"Expected 404 for PUT {path}, got {response.status_code}"
        )


class TestAdminRouteResponseBodies:
    """Verify 404 responses do not contain authentication-related content."""

    @pytest.mark.parametrize("path", ADMIN_GET_ROUTES[:3])
    def test_no_auth_content_in_404(self, guest_client: TestClient, path: str) -> None:
        """404 response body does not contain login/auth prompts."""
        response = guest_client.get(path)
        assert response.status_code == 404
        body = response.text.lower()
        assert "login" not in body
        assert "unauthorized" not in body
        assert "authenticate" not in body
