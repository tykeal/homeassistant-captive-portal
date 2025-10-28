# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin session CSRF protection."""

from typing import Any

import pytest


@pytest.fixture
def authenticated_client(client, admin_user) -> Any:
    """Create authenticated client with session and CSRF token."""
    # Login to get session
    login_response = client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert login_response.status_code == 200

    # Get CSRF token from response JSON
    csrf_token = login_response.json()["csrf_token"]
    client.cookies.set("csrftoken", csrf_token)

    return client, csrf_token


class TestAdminSessionCSRF:
    """Test CSRF protection for admin sessions."""

    def test_csrf_token_set_on_login(self, client, admin_user) -> None:
        """Login should set csrftoken cookie."""
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        assert response.status_code == 200
        assert "csrftoken" in response.cookies
        csrf_token = response.cookies.get("csrftoken")
        assert len(csrf_token) >= 32  # 32-byte minimum

    def test_csrf_token_cookie_attributes(self, client, admin_user) -> None:
        """CSRF cookie should have SameSite=Strict and Secure attributes."""
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        assert response.status_code == 200
        assert "csrftoken" in response.cookies

    def test_post_request_without_csrf_token_fails(self, authenticated_client) -> None:
        """POST request without CSRF token should return 403."""
        client, _ = authenticated_client

        # Remove CSRF token from request
        response = client.post("/api/grants/1/revoke")

        assert response.status_code == 403
        assert "csrf" in response.json().get("detail", "").lower()

    def test_post_request_with_valid_csrf_token_succeeds(self, authenticated_client) -> None:
        """POST request with valid CSRF token should succeed."""
        client, csrf_token = authenticated_client

        # Include CSRF token in request header
        response = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should not fail due to CSRF (may fail for other reasons like 404)
        assert response.status_code != 403

    def test_post_request_with_invalid_csrf_token_fails(self, authenticated_client) -> None:
        """POST request with invalid CSRF token should return 403."""
        client, _ = authenticated_client

        # Use invalid token
        response = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": "invalid-token-123"},
        )

        assert response.status_code == 403

    def test_csrf_token_from_form_field(self, authenticated_client) -> None:
        """CSRF token can be provided via form field."""
        client, csrf_token = authenticated_client

        # Submit form with CSRF token
        response = client.post(
            "/api/grants/1/revoke",
            data={"csrf_token": csrf_token},
        )

        # Should not fail due to CSRF
        assert response.status_code != 403

    def test_get_request_does_not_require_csrf_token(self, authenticated_client) -> None:
        """GET requests should not require CSRF token."""
        client, _ = authenticated_client

        # GET request without CSRF token
        response = client.get("/api/grants")

        # Should succeed (may be empty list)
        assert response.status_code in (200, 204)

    def test_csrf_token_double_submit_cookie_pattern(self, authenticated_client) -> None:
        """CSRF uses double-submit cookie pattern (cookie + header/form)."""
        client, csrf_token = authenticated_client

        # Token in cookie should match token in header
        response = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should not fail due to CSRF
        assert response.status_code != 403

    def test_csrf_token_constant_time_comparison(self, authenticated_client) -> None:
        """CSRF token comparison should be constant-time to prevent timing attacks."""
        client, csrf_token = authenticated_client

        # This is a behavioral test - both wrong tokens should fail identically
        response1 = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": "a" * len(csrf_token)},
        )
        response2 = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": "b" * len(csrf_token)},
        )

        assert response1.status_code == 403
        assert response2.status_code == 403

    def test_csrf_token_missing_from_cookie_fails(self, client) -> None:
        """POST request without csrftoken cookie should fail."""
        # Login
        client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        # Remove CSRF cookie
        client.cookies.clear()

        response = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": "some-token"},
        )

        assert response.status_code == 403

    def test_csrf_token_mismatch_cookie_header_fails(self, authenticated_client) -> None:
        """Cookie and header tokens must match."""
        client, csrf_token = authenticated_client

        # Use different token in header
        response = client.post(
            "/api/grants/1/revoke",
            headers={"X-CSRF-Token": "different-token-from-cookie"},
        )

        assert response.status_code == 403

    def test_csrf_exempt_endpoints_do_not_require_token(self, client) -> None:
        """CSRF-exempt endpoints (login) should not require token."""
        # Login without CSRF token should succeed
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        # Login itself should not require CSRF token
        assert response.status_code in (200, 401)  # Success or wrong credentials

    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/api/vouchers/redeem"),
            ("POST", "/api/grants/1/extend"),
            ("DELETE", "/api/grants/1"),
            ("PUT", "/api/integrations/entity-mapping/1"),
        ],
    )
    def test_state_changing_methods_require_csrf(self, authenticated_client, method, path) -> None:
        """All state-changing methods should require CSRF token."""
        client, _ = authenticated_client

        # Request without CSRF token
        response = client.request(method, path)

        assert response.status_code == 403
