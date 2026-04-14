# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests verifying all admin routes return 404 on guest app.

Admin routes are derived dynamically from create_app() so the test
suite automatically covers any new admin routers added in the future.
"""

import re
from collections.abc import Generator
from functools import lru_cache

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from captive_portal.app import create_app
from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app

_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


@lru_cache(maxsize=1)
def _admin_only_routes() -> tuple[tuple[str, str], ...]:
    """Return (method, path) pairs present on admin app but not guest app.

    Parameterised path segments (e.g. ``{grant_id}``) are replaced with a
    placeholder value so that the test client can issue a real request.
    Cached so the apps are only built once per process.
    """
    settings = AppSettings(db_path=":memory:")
    admin_app = create_app(settings=settings)
    guest_app = create_guest_app(settings=settings)

    def _route_set(app: FastAPI) -> set[tuple[str, str]]:
        """Extract (method, path) pairs from an app's routes."""
        routes: set[tuple[str, str]] = set()
        for route in app.routes:
            if isinstance(route, APIRoute):
                for method in route.methods or []:
                    routes.add((method.upper(), route.path))
        return routes

    admin_routes = _route_set(admin_app)
    guest_routes = _route_set(guest_app)
    admin_only = sorted(admin_routes - guest_routes)

    result: list[tuple[str, str]] = []
    for method, path in admin_only:
        concrete = re.sub(r"\{[^}]+\}", _PLACEHOLDER, path)
        result.append((method, concrete))
    return tuple(result)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically parametrize admin route tests at generation time."""
    if "admin_method" in metafunc.fixturenames and "admin_path" in metafunc.fixturenames:
        routes = _admin_only_routes()
        ids = [f"{m} {p}" for m, p in routes]
        metafunc.parametrize(("admin_method", "admin_path"), list(routes), ids=ids)


@pytest.fixture
def guest_app() -> FastAPI:
    """Create guest app for admin route isolation testing."""
    return create_guest_app(settings=AppSettings(db_path=":memory:"))


@pytest.fixture
def guest_client(guest_app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client for the guest app (no lifespan needed for 404 checks)."""
    with TestClient(guest_app, raise_server_exceptions=False) as client:
        yield client


class TestAdminRoutesReturn404OnGuest:
    """Verify every admin-only route returns 404 Not Found on guest listener."""

    def test_admin_route_returns_404(
        self, guest_client: TestClient, admin_method: str, admin_path: str
    ) -> None:
        """Admin route returns 404 (not 401/403) on guest app."""
        response = guest_client.request(
            admin_method, admin_path, json={} if admin_method != "GET" else None
        )
        assert response.status_code == 404, (
            f"Expected 404 for {admin_method} {admin_path}, got {response.status_code}"
        )


class TestAdminRouteResponseBodies:
    """Verify 404 responses do not contain authentication-related content."""

    @pytest.mark.parametrize(
        "path",
        ["/admin/portal-settings/", "/admin/docs", "/admin/redoc"],
    )
    def test_no_auth_content_in_404(self, guest_client: TestClient, path: str) -> None:
        """404 response body does not contain login/auth prompts."""
        response = guest_client.get(path)
        assert response.status_code == 404
        body = response.text.lower()
        assert "login" not in body
        assert "unauthorized" not in body
        assert "authenticate" not in body
