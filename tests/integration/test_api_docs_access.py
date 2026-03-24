# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
# mypy: disable-error-code="no-untyped-call"

"""Integration tests for admin-only API documentation access."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser


@pytest.fixture
def authenticated_admin(client: TestClient, db_session: Session) -> dict[str, Any]:
    """Create and authenticate an admin user.

    Args:
        client: Test client fixture
        db_session: Database session fixture

    Returns:
        Dictionary with admin credentials and session info
    """
    # Clear all admins
    admins = list(db_session.exec(select(AdminUser)).all())
    for admin in admins:
        db_session.delete(admin)
    db_session.commit()

    # Bootstrap first admin
    client.post(
        "/api/admin/auth/bootstrap",
        json={
            "username": "admin",
            "password": "SecureBootstrap123!",
            "email": "admin@example.com",
        },
    )

    # Login to get session
    login_response = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": "SecureBootstrap123!"},
    )

    return {
        "username": "admin",
        "password": "SecureBootstrap123!",
        "session_id": login_response.cookies.get("session_id"),
        "csrf_token": login_response.json().get("csrf_token"),
    }


class TestAPIDocsAccess:
    """Test suite for admin-only API documentation endpoints."""

    def test_swagger_ui_requires_admin_auth(self, client: TestClient) -> None:
        """Verify Swagger UI requires admin authentication.

        Args:
            client: Test client fixture
        """
        response = client.get("/admin/docs")
        assert response.status_code == 401

    def test_redoc_requires_admin_auth(self, client: TestClient) -> None:
        """Verify ReDoc requires admin authentication.

        Args:
            client: Test client fixture
        """
        response = client.get("/admin/redoc")
        assert response.status_code == 401

    def test_swagger_ui_accessible_to_admin(
        self, client: TestClient, authenticated_admin: dict[str, Any]
    ) -> None:
        """Verify Swagger UI is accessible to authenticated admin.

        Args:
            client: Test client fixture
            authenticated_admin: Authenticated admin fixture
        """
        client.cookies.set("session_id", authenticated_admin["session_id"])
        response = client.get("/admin/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "swagger" in response.text.lower()

    def test_redoc_accessible_to_admin(
        self, client: TestClient, authenticated_admin: dict[str, Any]
    ) -> None:
        """Verify ReDoc is accessible to authenticated admin.

        Args:
            client: Test client fixture
            authenticated_admin: Authenticated admin fixture
        """
        client.cookies.set("session_id", authenticated_admin["session_id"])
        response = client.get("/admin/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "redoc" in response.text.lower()

    def test_docs_endpoints_not_in_openapi_schema(
        self, client: TestClient, authenticated_admin: dict[str, Any]
    ) -> None:
        """Verify docs endpoints are excluded from OpenAPI schema.

        Args:
            client: Test client fixture
            authenticated_admin: Authenticated admin fixture
        """
        client.cookies.set("session_id", authenticated_admin["session_id"])
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        # Docs endpoints should not appear in schema (include_in_schema=False)
        assert "/admin/docs" not in schema["paths"]
        assert "/admin/redoc" not in schema["paths"]
