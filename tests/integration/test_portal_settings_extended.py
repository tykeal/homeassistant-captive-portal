# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for extended portal settings (session + guest fields)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser, AdminRole
from captive_portal.models.portal_config import PortalConfig


@pytest.fixture
def admin_role_user(db_session: Session) -> Generator[AdminUser, None, None]:
    """Create an admin-role user for testing.

    Args:
        db_session: Database session.

    Yields:
        AdminUser with admin role.
    """
    from captive_portal.security.password_hashing import hash_password

    user = AdminUser(
        username="settingsadmin",
        password_hash=hash_password("SecureP@ss123"),
        email="settingsadmin@example.com",
        role=AdminRole.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def authenticated_client(client: TestClient, admin_role_user: AdminUser) -> TestClient:
    """Return a client with an authenticated admin session.

    Args:
        client: Test HTTP client.
        admin_role_user: Admin user fixture.

    Returns:
        Authenticated TestClient.
    """
    response = client.post(
        "/api/admin/auth/login",
        json={"username": "settingsadmin", "password": "SecureP@ss123"},
    )
    assert response.status_code == 200
    csrf_token = response.json().get("csrf_token", "")
    if csrf_token:
        client.cookies.delete("csrftoken")
        client.cookies.set("csrftoken", csrf_token)
    return client


class TestPortalSettingsExtended:
    """Tests for extended portal settings fields."""

    def _get_csrf_token(self, client: TestClient) -> str:
        """Extract CSRF token from client cookies.

        Args:
            client: Authenticated test client.

        Returns:
            CSRF token string.
        """
        return client.cookies.get("csrftoken") or ""

    def test_form_shows_session_fields(self, authenticated_client: TestClient) -> None:
        """GET shows session timeout fields in form."""
        response = authenticated_client.get("/admin/portal-settings/")
        assert response.status_code == 200
        assert "session_idle_minutes" in response.text
        assert "session_max_hours" in response.text

    def test_form_shows_guest_url_field(self, authenticated_client: TestClient) -> None:
        """GET shows guest external URL field in form."""
        response = authenticated_client.get("/admin/portal-settings/")
        assert response.status_code == 200
        assert "guest_external_url" in response.text

    def test_saves_session_timeout(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """POST saves session timeout values."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data={
                "csrf_token": csrf_token,
                "rate_limit_attempts": "5",
                "rate_limit_window_seconds": "60",
                "success_redirect_url": "/guest/welcome",
                "session_idle_minutes": "45",
                "session_max_hours": "12",
                "guest_external_url": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "success" in response.headers.get("location", "")

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.session_idle_minutes == 45
        assert config.session_max_hours == 12

    def test_saves_guest_external_url(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """POST saves guest external URL."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data={
                "csrf_token": csrf_token,
                "rate_limit_attempts": "5",
                "rate_limit_window_seconds": "60",
                "success_redirect_url": "/guest/welcome",
                "session_idle_minutes": "30",
                "session_max_hours": "8",
                "guest_external_url": "https://guest.example.com",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://guest.example.com"

    def test_api_saves_ipv6_guest_external_url(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT saves guest external URLs with IPv6 literal hosts."""
        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": "https://[::1]:8443"},
        )

        assert response.status_code == 200

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://[::1]:8443"

    def test_rejects_invalid_guest_external_url(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """POST rejects unsafe guest external URLs without saving them."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data={
                "csrf_token": csrf_token,
                "rate_limit_attempts": "5",
                "rate_limit_window_seconds": "60",
                "success_redirect_url": "/guest/welcome",
                "session_idle_minutes": "30",
                "session_max_hours": "8",
                "guest_external_url": ("https://guest.example.com\r\nSet-Cookie: session=evil"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error" in response.headers.get("location", "")

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_api_rejects_invalid_guest_external_url(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT rejects unsafe guest external URLs without saving them."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": "https://guest.example.com/?next=evil"},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "guest_external_url" in detail
        assert "Guest external URL must be" in detail
        assert "+" not in detail

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_api_rejects_encoded_hostname_delimiter(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT rejects hostnames that IDNA-decode to delimiters."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": ("https://guest.example.com%EF%BC%BCevil.example")},
        )

        assert response.status_code == 422
        assert "guest_external_url" in response.text

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_api_rejects_empty_query_delimiter(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT rejects guest URLs with an empty query delimiter."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": "https://guest.example.com?"},
        )

        assert response.status_code == 422
        assert "guest_external_url" in response.text

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_api_rejects_guest_url_path(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT rejects guest URLs with paths before redirect suffixes."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": "https://guest.example.com/base"},
        )

        assert response.status_code == 422
        assert "guest_external_url" in response.text

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_api_rejects_encoded_authority_delimiter(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT rejects URLs with encoded authority delimiters."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": "https://guest.example.com%3A999999"},
        )

        assert response.status_code == 422
        assert "guest_external_url" in response.text

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_api_rejects_userinfo_authority_delimiter(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """PUT rejects URLs with userinfo authority delimiters."""
        db_session.merge(PortalConfig(id=1, guest_external_url="https://safe.example.com"))
        db_session.commit()

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"guest_external_url": "https://guest.example.com@evil.example"},
        )

        assert response.status_code == 422
        assert "guest_external_url" in response.text

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.guest_external_url == "https://safe.example.com"

    def test_rejects_invalid_session_idle(self, authenticated_client: TestClient) -> None:
        """POST rejects out-of-range session idle timeout."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data={
                "csrf_token": csrf_token,
                "rate_limit_attempts": "5",
                "rate_limit_window_seconds": "60",
                "success_redirect_url": "/guest/welcome",
                "session_idle_minutes": "0",
                "session_max_hours": "8",
                "guest_external_url": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error" in response.headers.get("location", "")

    def test_rejects_invalid_session_max(self, authenticated_client: TestClient) -> None:
        """POST rejects out-of-range session max hours."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data={
                "csrf_token": csrf_token,
                "rate_limit_attempts": "5",
                "rate_limit_window_seconds": "60",
                "success_redirect_url": "/guest/welcome",
                "session_idle_minutes": "30",
                "session_max_hours": "200",
                "guest_external_url": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error" in response.headers.get("location", "")
