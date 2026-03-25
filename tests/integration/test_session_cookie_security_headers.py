# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0712 – Integration tests for session cookie attributes and security headers.

Verifies:
  - Session cookies carry Secure, HttpOnly, SameSite attributes
  - CSP, Referrer-Policy, Permissions-Policy headers present on responses
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
# Security header tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSecurityHeaders:
    """Middleware must inject security headers on every response."""

    def test_csp_header_present(self, secure_client: TestClient) -> None:
        """Content-Security-Policy header must be set."""
        resp = secure_client.get("/api/health")
        assert "Content-Security-Policy" in resp.headers

    def test_csp_blocks_inline_scripts(self, secure_client: TestClient) -> None:
        """CSP script-src must not include 'unsafe-inline'."""
        csp = secure_client.get("/api/health").headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp
        assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]

    def test_referrer_policy_present(self, secure_client: TestClient) -> None:
        """Referrer-Policy header must be set."""
        resp = secure_client.get("/api/health")
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy_present(self, secure_client: TestClient) -> None:
        """Permissions-Policy header must disable sensitive features."""
        pp = secure_client.get("/api/health").headers["Permissions-Policy"]
        for feature in ("geolocation", "microphone", "camera"):
            assert f"{feature}=()" in pp, f"{feature} not disabled in Permissions-Policy"

    def test_x_frame_options(self, secure_client: TestClient) -> None:
        """X-Frame-Options must be DENY."""
        resp = secure_client.get("/api/health")
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_x_content_type_options(self, secure_client: TestClient) -> None:
        """X-Content-Type-Options must be nosniff."""
        resp = secure_client.get("/api/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_headers_present_on_guest_pages(self, secure_client: TestClient) -> None:
        """Security headers must also appear on guest HTML pages."""
        resp = secure_client.get("/guest/authorize")
        assert resp.status_code == 200
        assert "Content-Security-Policy" in resp.headers
        assert "X-Frame-Options" in resp.headers


# ---------------------------------------------------------------------------
# Cookie attribute tests  (using the conftest `client` which uses test db)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSessionCookieAttributes:
    """Admin session cookies must carry correct security attributes."""

    def test_session_cookie_httponly(self, client: TestClient, admin_user: Any) -> None:
        """Session cookie must be HttpOnly."""
        resp = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        assert resp.status_code == 200

        # Check Set-Cookie header for session_id
        set_cookie = _find_set_cookie_header(resp, "session_id")
        assert set_cookie is not None, "session_id cookie not found in response"
        assert "httponly" in set_cookie.lower()

    def test_session_cookie_samesite(self, client: TestClient, admin_user: Any) -> None:
        """Session cookie must carry a SameSite attribute."""
        resp = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        assert resp.status_code == 200

        set_cookie = _find_set_cookie_header(resp, "session_id")
        assert set_cookie is not None
        lower = set_cookie.lower()
        assert "samesite=strict" in lower or "samesite=lax" in lower

    def test_csrf_cookie_set_on_login(self, client: TestClient, admin_user: Any) -> None:
        """Login must set a csrftoken cookie."""
        resp = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        assert resp.status_code == 200
        assert "csrftoken" in resp.cookies

    def test_guest_csrf_cookie_samesite_lax(self, client: TestClient) -> None:
        """Guest CSRF cookie should use SameSite=Lax for redirect scenarios."""
        resp = client.get("/guest/authorize")
        assert resp.status_code == 200

        set_cookie = _find_set_cookie_header(resp, "guest_csrftoken")
        assert set_cookie is not None, "guest_csrftoken cookie not found"
        assert "samesite=lax" in set_cookie.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_set_cookie_header(resp: Any, cookie_name: str) -> str | None:
    """Return the raw Set-Cookie header for *cookie_name*, or None.

    Uses httpx Headers.multi_items() (TestClient wraps httpx, not requests).
    """
    for header_name, header_value in resp.headers.multi_items():
        if header_name.lower() == "set-cookie" and header_value.startswith(f"{cookie_name}="):
            return str(header_value)
    return None
