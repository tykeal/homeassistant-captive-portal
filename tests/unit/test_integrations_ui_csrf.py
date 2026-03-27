# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for CSRF cookie handling in integrations GET handlers.

The ``list_integrations`` and ``edit_integration`` GET handlers must set
the ``csrftoken`` cookie when one is not already present, so that the
double-submit cookie pattern works on subsequent POST requests.

A previous version generated the CSRF token for the form hidden field
but never called ``csrf.set_csrf_cookie()``, causing "CSRF token
validation failed" errors on form submission.
"""

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


def _login(client: TestClient) -> str:
    """Authenticate as admin and return the CSRF token."""
    resp = client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    csrf_token: str = resp.json()["csrf_token"]
    client.cookies.set("csrftoken", csrf_token)
    return csrf_token


def _make_integration(session: Session) -> UUID:
    """Create a test integration and return its id."""
    integration = HAIntegrationConfig(
        integration_id="test_csrf_integration",
        identifier_attr=IdentifierAttr.SLOT_NAME,
        checkout_grace_minutes=15,
    )
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration.id


class TestListIntegrationsCsrfCookie:
    """GET /admin/integrations/ must set the CSRF cookie."""

    def test_sets_csrf_cookie_when_absent(
        self,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """First visit (no csrftoken cookie) must set one on the response."""
        _login(client)
        # Clear the CSRF cookie so the GET handler must set a fresh one.
        client.cookies.delete("csrftoken")

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        assert "csrftoken" in resp.cookies, "GET /admin/integrations/ did not set csrftoken cookie"
        token = resp.cookies["csrftoken"]
        assert len(token) >= 32

    def test_reuses_existing_csrf_token(
        self,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """When a csrftoken cookie already exists, the handler reuses it."""
        _login(client)
        # Clear, then set a known token so we can verify reuse.
        client.cookies.delete("csrftoken")
        client.cookies.set("csrftoken", "known-token-for-reuse-test-0123456789ab")

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        # The response should NOT set a new cookie when one already exists.
        assert "csrftoken" not in resp.cookies, (
            "GET /admin/integrations/ overwrote an existing csrftoken cookie"
        )


class TestEditIntegrationCsrfCookie:
    """GET /admin/integrations/edit/{id} must set the CSRF cookie."""

    def test_sets_csrf_cookie_when_absent(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """First visit (no csrftoken cookie) must set one on the response."""
        _login(client)
        integration_id = _make_integration(db_session)
        # Clear the CSRF cookie so the GET handler must set a fresh one.
        client.cookies.delete("csrftoken")

        resp = client.get(f"/admin/integrations/edit/{integration_id}")

        assert resp.status_code == 200
        assert "csrftoken" in resp.cookies, (
            "GET /admin/integrations/edit/ did not set csrftoken cookie"
        )
        token = resp.cookies["csrftoken"]
        assert len(token) >= 32

    def test_reuses_existing_csrf_token(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """When a csrftoken cookie already exists, the handler reuses it."""
        _login(client)
        integration_id = _make_integration(db_session)
        # Clear, then set a known token so we can verify reuse.
        client.cookies.delete("csrftoken")
        client.cookies.set("csrftoken", "known-token-for-reuse-test-0123456789ab")

        resp = client.get(f"/admin/integrations/edit/{integration_id}")

        assert resp.status_code == 200
        # The response should NOT set a new cookie when one already exists.
        assert "csrftoken" not in resp.cookies, (
            "GET /admin/integrations/edit/ overwrote an existing csrftoken cookie"
        )
