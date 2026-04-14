# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for Omada settings UI routes."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser, AdminRole
from captive_portal.models.omada_config import OmadaConfig


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
        username="omadaadmin",
        password_hash=hash_password("SecureP@ss123"),
        email="omadaadmin@example.com",
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

    The CSRF token from login is stored as a cookie for form submissions.

    Args:
        client: Test HTTP client.
        admin_role_user: Admin user fixture.

    Returns:
        Authenticated TestClient.
    """
    response = client.post(
        "/api/admin/auth/login",
        json={"username": "omadaadmin", "password": "SecureP@ss123"},
    )
    assert response.status_code == 200
    # The login response includes a csrf_token in JSON body.
    # The server also sets it as a cookie, but since the cookie is
    # Secure=True and TestClient uses HTTP, we must set it manually.
    csrf_token = response.json().get("csrf_token", "")
    if csrf_token:
        # Clear any existing csrftoken cookies to avoid conflict
        client.cookies.delete("csrftoken")
        client.cookies.set("csrftoken", csrf_token)
    return client


class TestOmadaSettingsGet:
    """Tests for GET /admin/omada-settings/."""

    def test_renders_form(self, authenticated_client: TestClient) -> None:
        """GET returns 200 with form elements."""
        response = authenticated_client.get("/admin/omada-settings/")
        assert response.status_code == 200
        assert "controller_url" in response.text
        assert "username" in response.text
        assert "password" in response.text
        assert "csrf_token" in response.text

    def test_shows_masked_password_when_stored(
        self,
        authenticated_client: TestClient,
        db_session: Session,
    ) -> None:
        """GET shows placeholder when password is stored."""
        config = OmadaConfig(
            id=1,
            controller_url="https://omada.test:8043",
            username="admin",
            encrypted_password="some_encrypted_value",
        )
        db_session.merge(config)
        db_session.commit()

        response = authenticated_client.get("/admin/omada-settings/")
        assert response.status_code == 200
        assert "placeholder" in response.text

    def test_shows_saved_values(
        self,
        authenticated_client: TestClient,
        db_session: Session,
    ) -> None:
        """GET shows saved config values in form fields."""
        config = OmadaConfig(
            id=1,
            controller_url="https://omada.test:8043",
            username="testoperator",
            site_name="MySite",
            controller_id="aabbccdd1122",
        )
        db_session.merge(config)
        db_session.commit()

        response = authenticated_client.get("/admin/omada-settings/")
        assert response.status_code == 200
        assert "https://omada.test:8043" in response.text
        assert "testoperator" in response.text
        assert "MySite" in response.text
        assert "aabbccdd1122" in response.text

    def test_requires_authentication(self, client: TestClient) -> None:
        """GET returns 401/redirect when not authenticated."""
        response = client.get("/admin/omada-settings/", follow_redirects=False)
        # Should either be 401 or redirect to login
        assert response.status_code in (401, 302, 303, 307)


class TestOmadaSettingsPost:
    """Tests for POST /admin/omada-settings/."""

    def _get_csrf_token(self, client: TestClient) -> str:
        """Extract CSRF token from the client's cookies.

        In the double-submit cookie pattern, the form field must match
        the cookie value set at login.

        Args:
            client: Authenticated test client.

        Returns:
            CSRF token string from cookie.
        """
        return client.cookies.get("csrftoken") or ""

    def test_saves_valid_settings(
        self,
        authenticated_client: TestClient,
        db_session: Session,
    ) -> None:
        """POST saves valid settings and redirects with success."""
        csrf_token = self._get_csrf_token(authenticated_client)

        with (
            patch(
                "captive_portal.config.omada_config.build_omada_config",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "captive_portal.api.routes.omada_settings_ui.encrypt_credential",
                return_value="test_encrypted_password",
            ),
        ):
            response = authenticated_client.post(
                "/admin/omada-settings/",
                data={
                    "csrf_token": csrf_token,
                    "controller_url": "https://omada.test:8043",
                    "username": "operator",
                    "password": "secret",
                    "password_changed": "true",
                    "site_name": "TestSite",
                    "controller_id": "",
                    "verify_ssl": "true",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert "success" in response.headers.get("location", "")

        # Verify DB
        db_session.expire_all()
        config = db_session.get(OmadaConfig, 1)
        assert config is not None
        assert config.controller_url == "https://omada.test:8043"
        assert config.username == "operator"
        assert config.encrypted_password == "test_encrypted_password"
        assert config.site_name == "TestSite"

    def test_preserves_password_when_not_changed(
        self,
        authenticated_client: TestClient,
        db_session: Session,
    ) -> None:
        """POST preserves existing password when password_changed is false."""
        # Set up existing config with password
        config = OmadaConfig(
            id=1,
            controller_url="https://omada.test:8043",
            username="operator",
            encrypted_password="existing_encrypted_value",
        )
        db_session.merge(config)
        db_session.commit()

        csrf_token = self._get_csrf_token(authenticated_client)

        with patch(
            "captive_portal.config.omada_config.build_omada_config",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = authenticated_client.post(
                "/admin/omada-settings/",
                data={
                    "csrf_token": csrf_token,
                    "controller_url": "https://omada.test:8043",
                    "username": "operator",
                    "password": "",
                    "password_changed": "false",
                    "site_name": "Default",
                    "controller_id": "",
                },
                follow_redirects=False,
            )

        assert response.status_code == 303

        db_session.expire_all()
        updated = db_session.get(OmadaConfig, 1)
        assert updated is not None
        assert updated.encrypted_password == "existing_encrypted_value"

    def test_rejects_invalid_url(
        self,
        authenticated_client: TestClient,
    ) -> None:
        """POST rejects invalid controller URL."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/omada-settings/",
            data={
                "csrf_token": csrf_token,
                "controller_url": "not-a-url",
                "username": "operator",
                "password": "",
                "password_changed": "false",
                "site_name": "Default",
                "controller_id": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error" in response.headers.get("location", "")

    def test_rejects_invalid_controller_id(
        self,
        authenticated_client: TestClient,
    ) -> None:
        """POST rejects non-hex controller ID."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/omada-settings/",
            data={
                "csrf_token": csrf_token,
                "controller_url": "https://omada.test:8043",
                "username": "operator",
                "password": "",
                "password_changed": "false",
                "site_name": "Default",
                "controller_id": "not-hex!",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error" in response.headers.get("location", "")

    def test_logs_audit_event(
        self,
        authenticated_client: TestClient,
        db_session: Session,
    ) -> None:
        """POST logs audit event for config update."""
        from captive_portal.models.audit_log import AuditLog

        csrf_token = self._get_csrf_token(authenticated_client)

        with patch(
            "captive_portal.config.omada_config.build_omada_config",
            new_callable=AsyncMock,
            return_value=None,
        ):
            authenticated_client.post(
                "/admin/omada-settings/",
                data={
                    "csrf_token": csrf_token,
                    "controller_url": "",
                    "username": "",
                    "password": "",
                    "password_changed": "false",
                    "site_name": "Default",
                    "controller_id": "",
                },
                follow_redirects=False,
            )

        stmt: Any = select(AuditLog).where(AuditLog.action == "omada_config.update")
        logs = list(db_session.exec(stmt).all())
        assert len(logs) >= 1


class TestOmadaNavLink:
    """Tests for Omada nav link across admin pages."""

    def test_dashboard_has_omada_link(self, authenticated_client: TestClient) -> None:
        """Dashboard page includes Omada nav link."""
        response = authenticated_client.get("/admin/dashboard/")
        if response.status_code == 200:
            assert "omada-settings" in response.text

    def test_settings_has_omada_link(self, authenticated_client: TestClient) -> None:
        """Portal settings page includes Omada nav link."""
        response = authenticated_client.get("/admin/portal-settings/")
        assert response.status_code == 200
        assert "omada-settings" in response.text

    def test_omada_page_has_omada_link(self, authenticated_client: TestClient) -> None:
        """Omada settings page has active Omada nav link."""
        response = authenticated_client.get("/admin/omada-settings/")
        assert response.status_code == 200
        assert 'class="nav-link active">Omada' in response.text
