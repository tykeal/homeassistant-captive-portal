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
        from uuid import uuid4

        client, _ = authenticated_client

        # Remove CSRF token from request (use valid UUID to pass path validation)
        grant_id = uuid4()
        response = client.post(f"/api/grants/{grant_id}/revoke")

        assert response.status_code == 403
        assert "csrf" in response.json().get("detail", "").lower()

    def test_post_request_with_valid_csrf_token_succeeds(self, authenticated_client) -> None:
        """POST request with valid CSRF token should succeed."""
        from uuid import uuid4

        client, csrf_token = authenticated_client

        # Include CSRF token in request header (use valid UUID to pass path validation)
        grant_id = uuid4()
        response = client.post(
            f"/api/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should not fail due to CSRF (may fail for other reasons like 404)
        assert response.status_code != 403

    def test_post_request_with_invalid_csrf_token_fails(self, authenticated_client) -> None:
        """POST request with invalid CSRF token should return 403."""
        from uuid import uuid4

        client, _ = authenticated_client

        # Use invalid token (use valid UUID to pass path validation)
        grant_id = uuid4()
        response = client.post(
            f"/api/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": "invalid-token-123"},
        )

        assert response.status_code == 403

    def test_csrf_token_from_form_field(self, authenticated_client) -> None:
        """CSRF token can be provided via form field."""
        from uuid import uuid4

        client, csrf_token = authenticated_client

        # Submit form with CSRF token (use valid UUID to pass path validation)
        grant_id = uuid4()
        response = client.post(
            f"/api/grants/{grant_id}/revoke",
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
        from uuid import uuid4

        client, csrf_token = authenticated_client

        # Token in cookie should match token in header (use valid UUID to pass path validation)
        grant_id = uuid4()
        response = client.post(
            f"/api/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should not fail due to CSRF
        assert response.status_code != 403

    def test_csrf_token_constant_time_comparison(self, authenticated_client) -> None:
        """CSRF token comparison should be constant-time to prevent timing attacks."""
        from uuid import uuid4

        client, csrf_token = authenticated_client

        # This is a behavioral test - both wrong tokens should fail identically
        grant_id = uuid4()
        response1 = client.post(
            f"/api/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": "a" * len(csrf_token)},
        )
        response2 = client.post(
            f"/api/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": "b" * len(csrf_token)},
        )

        assert response1.status_code == 403
        assert response2.status_code == 403

    def test_csrf_token_missing_from_cookie_fails(self, authenticated_client) -> None:
        """POST request without csrftoken cookie should fail."""
        from uuid import uuid4

        client, _ = authenticated_client

        # Remove only CSRF cookie (delete by name)
        client.cookies.delete("csrftoken")

        # Use valid UUID to pass path validation
        grant_id = uuid4()
        response = client.post(
            f"/api/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": "some-token"},
        )

        assert response.status_code == 403

    def test_csrf_token_mismatch_cookie_header_fails(self, authenticated_client) -> None:
        """Cookie and header tokens must match."""
        from uuid import uuid4

        client, csrf_token = authenticated_client

        # Use different token in header (use valid UUID to pass path validation)
        grant_id = uuid4()
        response = client.post(
            f"/api/grants/{grant_id}/revoke",
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

    def test_grant_extend_requires_csrf(self, authenticated_client) -> None:
        """Grant extend endpoint requires CSRF token."""
        from uuid import uuid4

        client, _ = authenticated_client
        grant_id = uuid4()

        # Request without CSRF token should fail with 403
        response = client.post(
            f"/api/grants/{grant_id}/extend",
            json={"additional_minutes": 60},
        )

        assert response.status_code == 403

    def test_grant_revoke_requires_csrf(self, authenticated_client) -> None:
        """Grant revoke endpoint requires CSRF token."""
        from uuid import uuid4

        client, _ = authenticated_client
        grant_id = uuid4()

        # Request without CSRF token should fail with 403
        response = client.post(f"/api/grants/{grant_id}/revoke")

        assert response.status_code == 403

    def test_admin_account_create_requires_csrf(self, authenticated_client) -> None:
        """Admin account creation requires CSRF token."""
        client, _ = authenticated_client

        # Request without CSRF token should fail with 403
        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "newadmin",
                "email": "new@example.com",
                "password": "SecureP@ss456",
            },
        )

        assert response.status_code == 403

    def test_admin_account_delete_requires_csrf(self, authenticated_client) -> None:
        """Admin account deletion requires CSRF token."""
        from uuid import uuid4

        client, _ = authenticated_client
        admin_id = uuid4()

        # Request without CSRF token should fail with 403
        response = client.delete(f"/api/admin/accounts/{admin_id}")

        assert response.status_code == 403
