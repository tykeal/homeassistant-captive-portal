# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
# mypy: disable-error-code="no-untyped-call"

"""Integration tests for auth status endpoint and first-run onboarding flow."""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser


class TestAuthStatusEndpoint:
    """Tests for GET /api/admin/auth/status."""

    def test_status_needs_setup_when_no_admins(
        self, client: TestClient, empty_admin_table: Any
    ) -> None:
        """Status should return needs_setup=true when no admin accounts exist."""
        response = client.get("/api/admin/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_setup"] is True

    def test_status_no_setup_when_admin_exists(self, client: TestClient, admin_user: Any) -> None:
        """Status should return needs_setup=false when an admin account exists."""
        response = client.get("/api/admin/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["needs_setup"] is False

    def test_status_no_auth_required(self, client: TestClient, empty_admin_table: Any) -> None:
        """Status endpoint should be accessible without authentication."""
        response = client.get("/api/admin/auth/status")

        assert response.status_code == 200

    def test_status_transitions_after_bootstrap(
        self, client: TestClient, empty_admin_table: Any
    ) -> None:
        """Status should transition from needs_setup=true to false after bootstrap."""
        # Before bootstrap
        before = client.get("/api/admin/auth/status")
        assert before.json()["needs_setup"] is True

        # Bootstrap admin
        client.post(
            "/api/admin/auth/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        # After bootstrap
        after = client.get("/api/admin/auth/status")
        assert after.json()["needs_setup"] is False


class TestFirstRunOnboardingFlow:
    """Tests for the full first-run onboarding flow via API."""

    def test_bootstrap_then_login_succeeds(
        self, client: TestClient, empty_admin_table: Any
    ) -> None:
        """After bootstrap, the new admin can immediately log in."""
        # Verify setup is needed
        status_resp = client.get("/api/admin/auth/status")
        assert status_resp.json()["needs_setup"] is True

        # Bootstrap
        bootstrap_resp = client.post(
            "/api/admin/auth/bootstrap",
            json={
                "username": "newadmin",
                "password": "SecureP@ss123",
                "email": "newadmin@example.com",
            },
        )
        assert bootstrap_resp.status_code == 201

        # Login with new credentials
        login_resp = client.post(
            "/api/admin/auth/login",
            json={"username": "newadmin", "password": "SecureP@ss123"},
        )
        assert login_resp.status_code == 200
        assert "session_id" in login_resp.cookies

    def test_bootstrap_sets_admin_role(
        self, client: TestClient, empty_admin_table: Any, db_session: Session
    ) -> None:
        """Bootstrapped account should have admin role in the database."""
        client.post(
            "/api/admin/auth/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        admin = db_session.exec(select(AdminUser).where(AdminUser.username == "admin")).first()
        assert admin is not None
        assert admin.role == "admin"

    def test_second_bootstrap_rejected_after_setup(
        self, client: TestClient, empty_admin_table: Any
    ) -> None:
        """Bootstrap should be rejected once an admin exists."""
        # First bootstrap succeeds
        resp1 = client.post(
            "/api/admin/auth/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )
        assert resp1.status_code == 201

        # Second bootstrap fails
        resp2 = client.post(
            "/api/admin/auth/bootstrap",
            json={
                "username": "hacker",
                "password": "EvilP@ss123",
                "email": "hacker@example.com",
            },
        )
        assert resp2.status_code == 409

        # Status still shows no setup needed
        status_resp = client.get("/api/admin/auth/status")
        assert status_resp.json()["needs_setup"] is False
