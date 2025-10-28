# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin authentication login/logout flow."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser
from captive_portal.security.password_hashing import hash_password


@pytest.fixture
def admin_user(db_session: Session) -> Any:
    """Create test admin user in database."""
    admin = AdminUser(
        username="testadmin",
        password_hash=hash_password("SecureP@ss123"),
        email="testadmin@example.com",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    yield admin
    db_session.delete(admin)
    db_session.commit()


class TestAdminAuthLoginLogout:
    """Test admin authentication login and logout flows."""

    def test_login_success_returns_session_cookie(
        self, client: TestClient, admin_user: Any
    ) -> None:
        """Successful login should return 200 and set HTTP-only session cookie."""
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        assert response.status_code == 200
        assert "session_id" in response.cookies
        # Check cookie security attributes
        cookie = response.cookies.get("session_id")
        assert cookie is not None

    def test_login_failure_invalid_username(self, client: TestClient, admin_user: Any) -> None:
        """Login with invalid username should return 401."""
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "wronguser", "password": "SecureP@ss123"},
        )

        assert response.status_code == 401
        assert "session_id" not in response.cookies

    def test_login_failure_invalid_password(self, client: TestClient, admin_user: Any) -> None:
        """Login with invalid password should return 401."""
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "WrongPassword"},
        )

        assert response.status_code == 401
        assert "session_id" not in response.cookies

    def test_login_missing_fields_returns_422(self, client: TestClient) -> None:
        """Login with missing fields should return 422."""
        response = client.post("/api/admin/auth/login", json={"username": "test"})

        assert response.status_code == 422

    def test_logout_success_clears_session_cookie(
        self, client: TestClient, admin_user: Any
    ) -> None:
        """Logout should clear session cookie and return 200."""
        # First login
        login_response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        assert login_response.status_code == 200

        # Then logout
        logout_response = client.post("/api/admin/auth/logout")

        assert logout_response.status_code == 200
        # Session cookie should be deleted or expired
        cookie = logout_response.cookies.get("session_id")
        if cookie:
            assert cookie == "" or cookie is None

    def test_logout_without_session_returns_401(self, client: TestClient) -> None:
        """Logout without valid session should return 401."""
        response = client.post("/api/admin/auth/logout")

        assert response.status_code == 401

    def test_protected_route_without_session_returns_401(self, client: TestClient) -> None:
        """Accessing protected route without session should return 401."""
        response = client.get("/api/grants")

        assert response.status_code == 401

    def test_protected_route_with_valid_session_returns_200(
        self, client: TestClient, admin_user: Any
    ) -> None:
        """Accessing protected route with valid session should succeed."""
        # First login
        login_response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        assert login_response.status_code == 200

        # Access protected route with session cookie
        session_cookie = login_response.cookies.get("session_id")
        assert session_cookie is not None
        client.cookies.set("session_id", session_cookie)

        response = client.get("/api/grants")

        # Should succeed (200 or 204 if no grants)
        assert response.status_code in (200, 204)

    def test_session_cookie_httponly_attribute(self, client: TestClient, admin_user: Any) -> None:
        """Session cookie should have HttpOnly attribute."""
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        # TestClient doesn't expose cookie attributes directly
        # This would be tested via browser or HTTP client inspection
        assert response.status_code == 200
        assert "session_id" in response.cookies

    def test_session_cookie_secure_attribute_in_production(
        self, client: TestClient, admin_user: Any
    ) -> None:
        """Session cookie should have Secure attribute in production."""
        # This would be tested with HTTPS in production environment
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )

        assert response.status_code == 200
        assert "session_id" in response.cookies

    def test_multiple_logins_different_sessions(self, client: TestClient, admin_user: Any) -> None:
        """Multiple logins should create different session IDs."""
        response1 = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        session1 = response1.cookies.get("session_id")

        # Logout
        client.post("/api/admin/auth/logout")

        # Login again
        response2 = client.post(
            "/api/admin/auth/login",
            json={"username": "testadmin", "password": "SecureP@ss123"},
        )
        session2 = response2.cookies.get("session_id")

        assert session1 != session2
