# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for captive portal detection on the guest listener."""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


@pytest.fixture
def guest_app() -> FastAPI:
    """Create guest app with default settings (no external URL)."""
    return create_guest_app(settings=AppSettings(db_path=":memory:"))


@pytest.fixture
def guest_client(guest_app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client for the guest app."""
    with TestClient(guest_app) as client:
        yield client


@pytest.fixture
def guest_app_with_url() -> FastAPI:
    """Create guest app (URL will be read from DB during lifespan)."""
    return create_guest_app(
        settings=AppSettings(
            db_path=":memory:",
        )
    )


@pytest.fixture
def guest_client_with_url(
    guest_app_with_url: FastAPI,
) -> Generator[TestClient, None, None]:
    """Create test client for the guest app with external URL."""
    with TestClient(guest_app_with_url) as client:
        yield client


# All 7 detection URLs
DETECTION_URLS = [
    "/generate_204",
    "/gen_204",
    "/connecttest.txt",
    "/ncsi.txt",
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/success.txt",
]


class TestCaptiveDetectGuestRelative:
    """Test captive detection on guest listener with relative paths (no external URL)."""

    @pytest.mark.parametrize("url", DETECTION_URLS)
    def test_detection_redirects_to_guest_authorize(
        self, guest_client: TestClient, url: str
    ) -> None:
        """All detection URLs redirect to /guest/authorize with relative path."""
        response = guest_client.get(url, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/guest/authorize"


class TestCaptiveDetectGuestExternalUrl:
    """Test captive detection without external URL (DB default is empty)."""

    @pytest.mark.parametrize("url", DETECTION_URLS)
    def test_detection_uses_relative_path(
        self, guest_client_with_url: TestClient, url: str
    ) -> None:
        """Detection URLs redirect using relative path when DB has no URL."""
        response = guest_client_with_url.get(url, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/guest/authorize"


class TestGuestAuthorizationAccess:
    """Test that guest authorization form is accessible without authentication."""

    def test_guest_authorize_loads_without_auth(self, guest_client: TestClient) -> None:
        """GET /guest/authorize returns 200 OK with HTML content."""
        response = guest_client.get("/guest/authorize")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_guest_authorize_post_exists(self, guest_app: FastAPI) -> None:
        """POST /guest/authorize endpoint is registered."""
        route_paths = [getattr(route, "path", None) for route in guest_app.routes]
        assert "/guest/authorize" in route_paths
