# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for extended portal settings (session + guest fields)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi import FastAPI
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

    def _portal_form(self, csrf_token: str, **overrides: str) -> dict[str, str]:
        """Build the complete portal settings form payload.

        Args:
            csrf_token: CSRF token to submit.
            overrides: Form values to override.

        Returns:
            Complete portal settings form data.
        """
        form = {
            "csrf_token": csrf_token,
            "rate_limit_attempts": "5",
            "rate_limit_window_seconds": "60",
            "success_redirect_url": "/guest/welcome",
            "redirect_to_original_url": "true",
            "session_idle_minutes": "30",
            "session_max_hours": "8",
            "guest_external_url": "",
        }
        form.update(overrides)
        return form

    def _get_csrf_token(self, client: TestClient) -> str:
        """Extract CSRF token from client cookies.

        Args:
            client: Authenticated test client.

        Returns:
            CSRF token string.
        """
        return client.cookies.get("csrftoken") or ""

    def _assert_redirect_response(self, response: Any, location: str) -> None:
        """Assert exact redirect response metadata for form submissions.

        Args:
            response: HTTP response to inspect.
            location: Expected redirect location header.
        """
        assert response.status_code == 303
        assert response.headers["location"] == location
        assert response.headers["content-length"] == "0"
        assert response.headers.get("set-cookie") is None
        assert dict(response.cookies) == {}

    def _assert_validation_response(self, response: Any, detail: list[dict[str, Any]]) -> None:
        """Assert exact FastAPI form validation response metadata.

        Args:
            response: HTTP response to inspect.
            detail: Expected validation detail payload.
        """
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
        assert response.headers.get("set-cookie") is None
        assert response.json() == {"detail": detail}

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

    def test_post_accepts_complete_form_contract(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """POST accepts every portal settings form field and persists them."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data=self._portal_form(
                csrf_token,
                rate_limit_attempts="7",
                rate_limit_window_seconds="120",
                success_redirect_url="/guest/done",
                redirect_to_original_url="true",
                session_idle_minutes="45",
                session_max_hours="12",
                guest_external_url="  https://guest.example.com  ",
            ),
            follow_redirects=False,
        )

        self._assert_redirect_response(
            response,
            "/admin/portal-settings?success=Portal+configuration+updated+successfully",
        )

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.rate_limit_attempts == 7
        assert config.rate_limit_window_seconds == 120
        assert config.success_redirect_url == "/guest/done"
        assert config.redirect_to_original_url is True
        assert config.session_idle_minutes == 45
        assert config.session_max_hours == 12
        assert config.guest_external_url == "https://guest.example.com"

    def test_post_uses_form_defaults_when_optional_fields_are_absent(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """POST applies handler defaults when optional form fields are absent."""
        csrf_token = self._get_csrf_token(authenticated_client)
        form = self._portal_form(csrf_token)
        for field_name in (
            "redirect_to_original_url",
            "session_idle_minutes",
            "session_max_hours",
            "guest_external_url",
        ):
            del form[field_name]

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data=form,
            follow_redirects=False,
        )

        self._assert_redirect_response(
            response,
            "/admin/portal-settings?success=Portal+configuration+updated+successfully",
        )

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.rate_limit_attempts == 5
        assert config.rate_limit_window_seconds == 60
        assert config.success_redirect_url == "/guest/welcome"
        assert config.redirect_to_original_url is False
        assert config.session_idle_minutes == 30
        assert config.session_max_hours == 8
        assert config.guest_external_url == ""

    def test_post_only_treats_true_checkbox_value_as_enabled(
        self, authenticated_client: TestClient, db_session: Session
    ) -> None:
        """POST preserves exact checkbox string coercion behavior."""
        db_session.merge(PortalConfig(id=1, redirect_to_original_url=True))
        db_session.commit()
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data=self._portal_form(csrf_token, redirect_to_original_url="on"),
            follow_redirects=False,
        )

        self._assert_redirect_response(
            response,
            "/admin/portal-settings?success=Portal+configuration+updated+successfully",
        )

        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.redirect_to_original_url is False

    @pytest.mark.parametrize(
        ("field_name", "field_value", "location"),
        [
            (
                "rate_limit_attempts",
                "0",
                "/admin/portal-settings?error=Rate+limit+attempts+must+be+between+1+and+1000",
            ),
            (
                "rate_limit_window_seconds",
                "3601",
                "/admin/portal-settings?error=Rate+limit+window+must+be+between+1+and+3600+seconds",
            ),
            (
                "success_redirect_url",
                "x" * 2049,
                "/admin/portal-settings?error=Redirect+URL+too+long+(max+2048+characters)",
            ),
            (
                "session_idle_minutes",
                "0",
                "/admin/portal-settings?error=Session+idle+timeout+must+be+between+1+and+1440+minutes",
            ),
            (
                "session_max_hours",
                "169",
                "/admin/portal-settings?error=Session+max+duration+must+be+between+1+and+168+hours",
            ),
            (
                "guest_external_url",
                "https://guest.example.com/?next=evil",
                "/admin/portal-settings?error=Guest+external+URL+must+be+an+HTTP+or+HTTPS+URL+with+a+host%2C+and+must+not+include+a+path%2C+query%2C+fragment%2C+trailing+slash%2C+or+control+characters",
            ),
        ],
    )
    def test_post_rejects_invalid_form_contract_values(
        self,
        authenticated_client: TestClient,
        db_session: Session,
        field_name: str,
        field_value: str,
        location: str,
    ) -> None:
        """POST redirects with exact errors for handler-level validation."""
        db_session.merge(PortalConfig(id=1, rate_limit_attempts=11))
        db_session.commit()
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data=self._portal_form(csrf_token, **{field_name: field_value}),
            follow_redirects=False,
        )

        self._assert_redirect_response(response, location)
        db_session.expire_all()
        config = db_session.get(PortalConfig, 1)
        assert config is not None
        assert config.rate_limit_attempts == 11

    @pytest.mark.parametrize(
        ("missing_field", "detail"),
        [
            (
                "csrf_token",
                [
                    {
                        "type": "missing",
                        "loc": ["body", "csrf_token"],
                        "msg": "Field required",
                        "input": None,
                    }
                ],
            ),
            (
                "rate_limit_attempts",
                [
                    {
                        "type": "missing",
                        "loc": ["body", "rate_limit_attempts"],
                        "msg": "Field required",
                        "input": None,
                    }
                ],
            ),
            (
                "rate_limit_window_seconds",
                [
                    {
                        "type": "missing",
                        "loc": ["body", "rate_limit_window_seconds"],
                        "msg": "Field required",
                        "input": None,
                    }
                ],
            ),
            (
                "success_redirect_url",
                [
                    {
                        "type": "missing",
                        "loc": ["body", "success_redirect_url"],
                        "msg": "Field required",
                        "input": None,
                    }
                ],
            ),
        ],
    )
    def test_post_rejects_missing_required_form_fields(
        self,
        authenticated_client: TestClient,
        missing_field: str,
        detail: list[dict[str, Any]],
    ) -> None:
        """POST returns exact validation errors for missing required fields."""
        csrf_token = self._get_csrf_token(authenticated_client)
        form = self._portal_form(csrf_token)
        del form[missing_field]

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data=form,
            follow_redirects=False,
        )

        self._assert_validation_response(response, detail)

    @pytest.mark.parametrize(
        ("field_name", "detail"),
        [
            (
                "rate_limit_attempts",
                [
                    {
                        "type": "int_parsing",
                        "loc": ["body", "rate_limit_attempts"],
                        "msg": "Input should be a valid integer, unable to parse string as an integer",
                        "input": "abc",
                    }
                ],
            ),
            (
                "rate_limit_window_seconds",
                [
                    {
                        "type": "int_parsing",
                        "loc": ["body", "rate_limit_window_seconds"],
                        "msg": "Input should be a valid integer, unable to parse string as an integer",
                        "input": "abc",
                    }
                ],
            ),
            (
                "session_idle_minutes",
                [
                    {
                        "type": "int_parsing",
                        "loc": ["body", "session_idle_minutes"],
                        "msg": "Input should be a valid integer, unable to parse string as an integer",
                        "input": "abc",
                    }
                ],
            ),
            (
                "session_max_hours",
                [
                    {
                        "type": "int_parsing",
                        "loc": ["body", "session_max_hours"],
                        "msg": "Input should be a valid integer, unable to parse string as an integer",
                        "input": "abc",
                    }
                ],
            ),
        ],
    )
    def test_post_rejects_invalid_integer_form_fields(
        self,
        authenticated_client: TestClient,
        field_name: str,
        detail: list[dict[str, Any]],
    ) -> None:
        """POST returns exact validation errors for invalid integer fields."""
        csrf_token = self._get_csrf_token(authenticated_client)

        response = authenticated_client.post(
            "/admin/portal-settings/",
            data=self._portal_form(csrf_token, **{field_name: "abc"}),
            follow_redirects=False,
        )

        self._assert_validation_response(response, detail)

    def test_refreshes_runtime_session_config(self, authenticated_client: TestClient) -> None:
        """POST applies saved session timeout values to app state."""
        csrf_token = self._get_csrf_token(authenticated_client)
        test_app = cast(FastAPI, authenticated_client.app)
        runtime_config = test_app.state.session_config
        assert runtime_config.idle_minutes == 30
        assert runtime_config.max_hours == 8

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
        assert runtime_config.idle_minutes == 45
        assert runtime_config.max_hours == 12
        assert runtime_config.cookie_secure is False

    def test_api_refreshes_runtime_session_config(self, authenticated_client: TestClient) -> None:
        """PUT applies saved session timeout values to app state."""
        test_app = cast(FastAPI, authenticated_client.app)
        runtime_config = test_app.state.session_config
        assert runtime_config.idle_minutes == 30
        assert runtime_config.max_hours == 8

        response = authenticated_client.put(
            "/api/admin/portal-config",
            json={"session_idle_minutes": 55, "session_max_hours": 14},
        )

        assert response.status_code == 200
        assert runtime_config.idle_minutes == 55
        assert runtime_config.max_hours == 14
        assert runtime_config.cookie_secure is False

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
