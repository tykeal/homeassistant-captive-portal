# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for security headers middleware."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Create test client with security headers middleware."""
    from captive_portal.app import create_app

    app = create_app()
    return TestClient(app)


def test_security_headers_on_health_endpoint(client: TestClient) -> None:
    """Verify security headers are present on health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200

    # Check required security headers
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Content-Security-Policy" in response.headers
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]


def test_security_headers_on_404(client: TestClient) -> None:
    """Verify security headers are present even on error responses."""
    response = client.get("/nonexistent-route")
    assert response.status_code == 404

    # Headers should still be present on error responses
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_csp_header_prevents_inline_scripts(client: TestClient) -> None:
    """Verify CSP header restricts script sources."""
    response = client.get("/api/health")

    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp  # Should not allow inline scripts


def test_permissions_policy_disables_features(client: TestClient) -> None:
    """Verify Permissions-Policy header disables unnecessary features."""
    response = client.get("/api/health")

    permissions = response.headers["Permissions-Policy"]
    # Check that sensitive features are disabled
    assert "geolocation=()" in permissions
    assert "microphone=()" in permissions
    assert "camera=()" in permissions


def test_referrer_policy_set(client: TestClient) -> None:
    """Verify Referrer-Policy header is set appropriately."""
    response = client.get("/api/health")

    assert "Referrer-Policy" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_security_headers_on_all_routes(client: TestClient) -> None:
    """Verify security headers are present on various routes."""
    routes = [
        "/api/health",
        "/success.txt",
        "/generate_204",
    ]

    for route in routes:
        response = client.get(route)
        # Don't check status code, just that headers are present
        assert "X-Frame-Options" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "Content-Security-Policy" in response.headers
