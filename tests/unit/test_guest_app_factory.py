# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the guest-only FastAPI app factory."""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


@pytest.fixture
def guest_settings() -> AppSettings:
    """Create test settings with in-memory database."""
    return AppSettings(db_path=":memory:")


@pytest.fixture
def guest_app(guest_settings: AppSettings) -> FastAPI:
    """Create guest app instance for testing."""
    return create_guest_app(settings=guest_settings)


@pytest.fixture
def guest_client(guest_app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client for the guest app.

    Uses context manager to trigger lifespan (DB initialization).
    """
    with TestClient(guest_app) as client:
        yield client


class TestGuestAppFactory:
    """Test create_guest_app() factory function."""

    def test_returns_fastapi_instance(self, guest_app: FastAPI) -> None:
        """create_guest_app() returns a FastAPI instance."""
        assert isinstance(guest_app, FastAPI)

    def test_with_in_memory_db(self) -> None:
        """create_guest_app works with in-memory DB settings."""
        settings = AppSettings(db_path=":memory:")
        app = create_guest_app(settings=settings)
        assert isinstance(app, FastAPI)


class TestGuestAppRoutes:
    """Test that guest app mounts exactly the right routers."""

    def test_captive_detect_generate_204(self, guest_client: TestClient) -> None:
        """Captive detection /generate_204 is mounted."""
        response = guest_client.get("/generate_204", follow_redirects=False)
        assert response.status_code == 302

    def test_captive_detect_gen_204(self, guest_client: TestClient) -> None:
        """Captive detection /gen_204 is mounted."""
        response = guest_client.get("/gen_204", follow_redirects=False)
        assert response.status_code == 302

    def test_captive_detect_connecttest(self, guest_client: TestClient) -> None:
        """Captive detection /connecttest.txt is mounted."""
        response = guest_client.get("/connecttest.txt", follow_redirects=False)
        assert response.status_code == 302

    def test_captive_detect_ncsi(self, guest_client: TestClient) -> None:
        """Captive detection /ncsi.txt is mounted."""
        response = guest_client.get("/ncsi.txt", follow_redirects=False)
        assert response.status_code == 302

    def test_captive_detect_hotspot(self, guest_client: TestClient) -> None:
        """Captive detection /hotspot-detect.html is mounted."""
        response = guest_client.get("/hotspot-detect.html", follow_redirects=False)
        assert response.status_code == 302

    def test_captive_detect_apple_alt(self, guest_client: TestClient) -> None:
        """Captive detection /library/test/success.html is mounted."""
        response = guest_client.get("/library/test/success.html", follow_redirects=False)
        assert response.status_code == 302

    def test_captive_detect_firefox(self, guest_client: TestClient) -> None:
        """Captive detection /success.txt is mounted."""
        response = guest_client.get("/success.txt", follow_redirects=False)
        assert response.status_code == 302

    def test_guest_authorize_get(self, guest_client: TestClient) -> None:
        """Guest authorization page /guest/authorize is mounted."""
        response = guest_client.get("/guest/authorize")
        assert response.status_code == 200

    def test_booking_authorize_post(self, guest_app: FastAPI) -> None:
        """Booking authorize /api/guest/authorize endpoint is registered."""
        route_paths = [getattr(route, "path", None) for route in guest_app.routes]
        assert "/api/guest/authorize" in route_paths

    def test_health_endpoint(self, guest_client: TestClient) -> None:
        """Health endpoint /api/health is mounted."""
        response = guest_client.get("/api/health")
        assert response.status_code == 200

    def test_ready_endpoint(self, guest_client: TestClient) -> None:
        """Readiness endpoint /api/ready is mounted."""
        response = guest_client.get("/api/ready")
        assert response.status_code == 200

    def test_live_endpoint(self, guest_client: TestClient) -> None:
        """Liveness endpoint /api/live is mounted."""
        response = guest_client.get("/api/live")
        assert response.status_code == 200


class TestGuestAppRootRedirect:
    """Test guest app root redirect to /guest/authorize."""

    def test_root_redirects_to_guest_authorize(self, guest_client: TestClient) -> None:
        """GET / returns 303 redirect to /guest/authorize."""
        response = guest_client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/guest/authorize"


class TestGuestAppSecurityHeaders:
    """Test that guest app has correct security headers."""

    def test_x_frame_options_deny(self, guest_client: TestClient) -> None:
        """Guest app sets X-Frame-Options to DENY (not framed)."""
        response = guest_client.get("/api/health")
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_csp_frame_ancestors_none(self, guest_client: TestClient) -> None:
        """Guest app CSP includes frame-ancestors 'none'."""
        response = guest_client.get("/api/health")
        csp = response.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp

    def test_csp_base_uri_self(self, guest_client: TestClient) -> None:
        """Guest app CSP includes base-uri 'self'."""
        response = guest_client.get("/api/health")
        csp = response.headers["Content-Security-Policy"]
        assert "base-uri 'self'" in csp

    def test_csp_form_action_self(self, guest_client: TestClient) -> None:
        """Guest app CSP includes form-action 'self'."""
        response = guest_client.get("/api/health")
        csp = response.headers["Content-Security-Policy"]
        assert "form-action 'self'" in csp


class TestGuestAppNoSessionMiddleware:
    """Test that guest app does NOT have SessionMiddleware."""

    def test_no_session_cookie(self, guest_client: TestClient) -> None:
        """Guest app does not set a session cookie on responses."""
        response = guest_client.get("/api/health")
        # SessionMiddleware would set a 'session_id' cookie
        cookies = response.cookies
        assert "session_id" not in cookies


class TestGuestAppState:
    """Test guest app state configuration."""

    def test_guest_external_url_in_state(self) -> None:
        """Guest app stores guest_external_url in app.state (default empty)."""
        settings = AppSettings(db_path=":memory:")
        app = create_guest_app(settings=settings)
        # Before lifespan runs, guest_external_url defaults to empty
        assert app.state.guest_external_url == ""

    def test_guest_external_url_empty_in_state(self, guest_app: FastAPI) -> None:
        """Guest app stores empty guest_external_url in state when not configured."""
        assert guest_app.state.guest_external_url == ""


class TestGuestAppStaticMount:
    """Test that static themes are mounted."""

    def test_static_themes_mount(self, guest_client: TestClient) -> None:
        """Static themes mount exists at /static/themes."""
        # Requesting a non-existent theme file should return 404 from StaticFiles,
        # not from the main router (which would be a different 404 structure)
        response = guest_client.get("/static/themes/nonexistent.css")
        assert response.status_code == 404
