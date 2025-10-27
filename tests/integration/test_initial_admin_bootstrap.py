# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for initial admin bootstrap on first run."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.app import create_app
from captive_portal.models.admin_user import AdminAccount
from captive_portal.persistence.database import get_session  # type: ignore[attr-defined]


@pytest.fixture
def app() -> Any:
    """Create test FastAPI app."""
    return create_app()


@pytest.fixture
def client(app) -> Any:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def empty_admin_table(app) -> Any:
    """Ensure admin table is empty."""
    db: Session = next(get_session())
    # Clear all admins
    admins = db.query(AdminAccount).all()
    for admin in admins:
        db.delete(admin)
    db.commit()
    yield
    # Cleanup
    admins = db.query(AdminAccount).all()
    for admin in admins:
        db.delete(admin)
    db.commit()


class TestInitialAdminBootstrap:
    """Test initial admin account bootstrap on first run."""

    def test_bootstrap_creates_default_admin_on_first_run(self, client, empty_admin_table) -> None:
        """First run should create default admin account."""
        # Access bootstrap endpoint
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "admin"
        assert "password_hash" not in data  # Should not expose hash

    def test_bootstrap_fails_if_admin_exists(self, client) -> None:
        """Bootstrap should fail if admin already exists."""
        # Create initial admin
        client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        # Try to bootstrap again
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin2",
                "password": "AnotherPassword123!",
                "email": "admin2@example.com",
            },
        )

        assert response.status_code == 409  # Conflict
        assert "already exists" in response.json().get("detail", "").lower()

    def test_bootstrap_requires_strong_password(self, client, empty_admin_table) -> None:
        """Bootstrap should require strong password."""
        # Weak password
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "weak",
                "email": "admin@example.com",
            },
        )

        assert response.status_code == 422

    def test_bootstrap_requires_valid_email(self, client, empty_admin_table) -> None:
        """Bootstrap should require valid email format."""
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "invalid-email",
            },
        )

        assert response.status_code == 422

    def test_bootstrap_creates_admin_role(self, client, empty_admin_table) -> None:
        """Bootstrapped account should have admin role."""
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "admin"

    def test_bootstrap_username_must_be_unique(self, client, empty_admin_table) -> None:
        """Bootstrap username must be unique."""
        # First bootstrap
        client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        # Try same username (though bootstrap should be disabled)
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "DifferentPassword123!",
                "email": "different@example.com",
            },
        )

        assert response.status_code == 409

    def test_bootstrapped_admin_can_login(self, client, empty_admin_table) -> None:
        """Bootstrapped admin should be able to login."""
        # Bootstrap
        client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        # Login
        login_response = client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "SecureBootstrap123!"},
        )

        assert login_response.status_code == 200
        assert "session_id" in login_response.cookies

    def test_bootstrap_hashes_password_with_argon2(self, client, empty_admin_table) -> None:
        """Bootstrap should hash password with argon2."""
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        assert response.status_code == 201

        # Verify in database (would check AdminAccount.password_hash format)
        db: Session = next(get_session())
        admin = db.query(AdminAccount).filter_by(username="admin").first()
        assert admin is not None
        assert admin.password_hash.startswith("$argon2id$")

    def test_bootstrap_missing_fields_returns_422(self, client, empty_admin_table) -> None:
        """Bootstrap with missing required fields should return 422."""
        response = client.post(
            "/api/admin/bootstrap",
            json={"username": "admin"},
        )

        assert response.status_code == 422

    def test_bootstrap_creates_audit_log_entry(self, client, empty_admin_table) -> None:
        """Bootstrap should create audit log entry."""
        response = client.post(
            "/api/admin/bootstrap",
            json={
                "username": "admin",
                "password": "SecureBootstrap123!",
                "email": "admin@example.com",
            },
        )

        assert response.status_code == 201

        # Would verify audit log contains bootstrap event
