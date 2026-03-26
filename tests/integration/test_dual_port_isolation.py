# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for complete dual-port route isolation.

Verifies that admin routes exist on the ingress app but return 404 on
the guest app, and that guest routes exist on both listeners.  Admin
routes are derived dynamically from the ingress app so the test suite
automatically covers any new admin routers.
"""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from captive_portal.app import create_app
from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


def _admin_only_get_paths() -> list[str]:
    """Return GET paths present on admin app but not guest app."""
    settings = AppSettings(db_path=":memory:")
    admin_app = create_app(settings=settings)
    guest_app = create_guest_app(settings=settings)

    def _get_paths(app: FastAPI) -> set[str]:
        """Extract concrete GET paths from an app's routes."""
        paths: set[str] = set()
        for route in app.routes:
            if isinstance(route, APIRoute) and "GET" in (route.methods or set()):
                concrete = route.path.replace("{grant_id}", "00000000-0000-0000-0000-000000000000")
                concrete = concrete.replace("{admin_id}", "00000000-0000-0000-0000-000000000000")
                concrete = concrete.replace(
                    "{integration_id}", "00000000-0000-0000-0000-000000000000"
                )
                concrete = concrete.replace("{config_id}", "00000000-0000-0000-0000-000000000000")
                paths.add(concrete)
        return paths

    return sorted(_get_paths(admin_app) - _get_paths(guest_app))


ADMIN_ROUTES = _admin_only_get_paths()

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

    @pytest.mark.parametrize("path", ADMIN_ROUTES)
    def test_admin_route_exists_on_ingress(self, ingress_client: TestClient, path: str) -> None:
        """Admin route returns non-404 on ingress app."""
        response = ingress_client.get(path)
        assert response.status_code != 404, (
            f"Expected non-404 for GET {path} on ingress, got {response.status_code}"
        )

    @pytest.mark.parametrize("path", ADMIN_ROUTES)
    def test_admin_route_404_on_guest(self, guest_client: TestClient, path: str) -> None:
        """Admin route returns 404 on guest app."""
        response = guest_client.get(path)
        assert response.status_code == 404, (
            f"Expected 404 for GET {path} on guest, got {response.status_code}"
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

    def test_guest_404_is_standard_json(self, guest_client: TestClient) -> None:
        """Guest app 404 for admin route returns standard FastAPI JSON."""
        response = guest_client.get("/api/grants/")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
