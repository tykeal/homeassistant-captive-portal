# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for complete dual-port route isolation.

Verifies that admin routes exist on the ingress app but return 404 on
the guest app, and that guest routes exist on both listeners.  Admin
routes are derived dynamically from the ingress app so the test suite
automatically covers any new admin routers.
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
def _admin_only_get_paths() -> tuple[str, ...]:
    """Return GET paths present on admin app but not guest app.

    Cached so the apps are only built once per process.
    """
    settings = AppSettings(db_path=":memory:")
    admin_app = create_app(settings=settings)
    guest_app = create_guest_app(settings=settings)

    def _get_paths(app: FastAPI) -> set[str]:
        """Extract concrete GET paths from an app's routes."""
        paths: set[str] = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and "GET" in (route.methods or set()):
                concrete = re.sub(r"\{[^}]+\}", _PLACEHOLDER, route.path)
                paths.add(concrete)
        return paths

    return tuple(sorted(_get_paths(admin_app) - _get_paths(guest_app)))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically parametrize admin route tests at generation time."""
    if "admin_path" in metafunc.fixturenames:
        metafunc.parametrize("admin_path", list(_admin_only_get_paths()))


# Guest routes: should exist on both
GUEST_ROUTES = [
    "/guest/authorize",
    "/generate_204",
    "/api/health",
]


@pytest.fixture
def settings() -> AppSettings:
    """Shared test settings."""
    return AppSettings(db_path=":memory:")


@pytest.fixture
def ingress_app(settings: AppSettings) -> FastAPI:
    """Create the ingress (main) app."""
    return create_app(settings=settings)


@pytest.fixture
def guest_app(settings: AppSettings) -> FastAPI:
    """Create the guest app."""
    return create_guest_app(settings=settings)


@pytest.fixture
def ingress_client(ingress_app: FastAPI) -> Generator[TestClient, None, None]:
    """Test client for ingress app (with lifespan)."""
    with TestClient(ingress_app) as client:
        yield client


@pytest.fixture
def guest_client(guest_app: FastAPI) -> Generator[TestClient, None, None]:
    """Test client for guest app (with lifespan)."""
    with TestClient(guest_app) as client:
        yield client


class TestDualPortAdminIsolation:
    """Test admin routes exist on ingress but not on guest."""

    def test_admin_route_exists_on_ingress(
        self, ingress_client: TestClient, admin_path: str
    ) -> None:
        """Admin route returns non-404 on ingress app."""
        response = ingress_client.get(admin_path)
        assert response.status_code != 404, (
            f"Expected non-404 for GET {admin_path} on ingress, got {response.status_code}"
        )

    def test_admin_route_404_on_guest(self, guest_client: TestClient, admin_path: str) -> None:
        """Admin route returns 404 on guest app."""
        response = guest_client.get(admin_path)
        assert response.status_code == 404, (
            f"Expected 404 for GET {admin_path} on guest, got {response.status_code}"
        )


class TestDualPortGuestShared:
    """Test guest routes exist on both listeners."""

    @pytest.mark.parametrize("path", GUEST_ROUTES)
    def test_guest_route_exists_on_ingress(self, ingress_client: TestClient, path: str) -> None:
        """Guest route returns non-404 on ingress app."""
        response = ingress_client.get(path, follow_redirects=False)
        assert response.status_code != 404, (
            f"Expected non-404 for GET {path} on ingress, got {response.status_code}"
        )

    @pytest.mark.parametrize("path", GUEST_ROUTES)
    def test_guest_route_exists_on_guest(self, guest_client: TestClient, path: str) -> None:
        """Guest route returns non-404 on guest app."""
        response = guest_client.get(path, follow_redirects=False)
        assert response.status_code != 404, (
            f"Expected non-404 for GET {path} on guest, got {response.status_code}"
        )


class TestDualPortResponseFormat:
    """Test that guest app 404 responses have standard format."""

    def test_guest_404_is_friendly_html(self, guest_client: TestClient) -> None:
        """Guest app 404 for admin route returns friendly HTML error page."""
        response = guest_client.get("/api/grants/")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert b"The requested resource was not found." in response.content
