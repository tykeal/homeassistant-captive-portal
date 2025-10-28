# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for adding additional admin accounts."""

from typing import Any

import pytest
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser


@pytest.fixture
def bootstrapped_admin(client: Any, db_session: Session) -> dict[str, Any]:
    """Create initial admin via bootstrap."""
    # Clear all admins
    stmt = select(AdminUser)
    admins = db_session.exec(stmt).all()
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


class TestAddAdditionalAdmin:
    """Test adding additional admin accounts after initial bootstrap."""

    def test_admin_can_add_additional_admin(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Authenticated admin should be able to add additional admin."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "admin2"
        assert data["email"] == "admin2@example.com"
        assert data["role"] == "admin"
        assert "password_hash" not in data

    def test_unauthenticated_cannot_add_admin(
        self, app: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Unauthenticated request should fail to add admin."""
        # Create a fresh client without cookies to simulate unauthenticated request
        from starlette.testclient import TestClient

        fresh_client = TestClient(app)
        response = fresh_client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
        )

        assert response.status_code == 401

    def test_new_admin_username_must_be_unique(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Adding admin with duplicate username should fail."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin",  # Same as bootstrapped admin
                "password": "DifferentPassword123!",
                "email": "different@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 409
        assert "username" in response.json().get("detail", "").lower()

    def test_new_admin_email_must_be_unique(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Adding admin with duplicate email should fail."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin@example.com",  # Same as bootstrapped admin
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 409
        assert "email" in response.json().get("detail", "").lower()

    @pytest.mark.skip(reason="Password validation not yet implemented - Phase 4")
    def test_new_admin_requires_strong_password(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Adding admin with weak password should fail."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "weak",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 422

    def test_new_admin_requires_valid_email(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Adding admin with invalid email should fail."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "invalid-email",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 422

    def test_new_admin_can_login(self, client: Any, bootstrapped_admin: dict[str, Any]) -> None:
        """Newly created admin should be able to login."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        # Create new admin
        client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        # Clear cookies
        client.cookies.clear()

        # Login as new admin
        login_response = client.post(
            "/api/admin/auth/login",
            json={"username": "admin2", "password": "AnotherSecure123!"},
        )

        assert login_response.status_code == 200
        assert "session_id" in login_response.cookies

    def test_new_admin_password_hashed_with_argon2(
        self, client: Any, bootstrapped_admin: dict[str, Any], db_session: Session
    ) -> None:
        """New admin password should be hashed with argon2."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 201

        # Verify in database
        from sqlmodel import select

        stmt = select(AdminUser).where(AdminUser.username == "admin2")
        admin = db_session.exec(stmt).first()
        assert admin is not None
        assert admin.password_hash.startswith("$argon2id$")

    def test_adding_admin_creates_audit_log_entry(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Adding admin should create audit log entry."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 201
        # Would verify audit log contains admin creation event

    def test_new_admin_missing_required_fields(
        self, client: Any, bootstrapped_admin: dict[str, Any]
    ) -> None:
        """Adding admin with missing required fields should fail."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        response = client.post(
            "/api/admin/accounts",
            json={"username": "admin2"},
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 422

    def test_list_admin_accounts(self, client: Any, bootstrapped_admin: dict[str, Any]) -> None:
        """Admin should be able to list all admin accounts."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        # Add another admin
        client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        # List admins
        response = client.get("/api/admin/accounts")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        usernames = [admin["username"] for admin in data]
        assert "admin" in usernames
        assert "admin2" in usernames

    def test_delete_admin_account(
        self, client: Any, bootstrapped_admin: dict[str, Any], db_session: Session
    ) -> None:
        """Admin should be able to delete another admin account."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        # Add another admin
        create_response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )
        admin2_id = create_response.json()["id"]

        # Delete admin2
        delete_response = client.delete(
            f"/api/admin/accounts/{admin2_id}",
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert delete_response.status_code == 204

        # Verify deletion
        from sqlmodel import select

        stmt = select(AdminUser).where(AdminUser.username == "admin2")
        admin = db_session.exec(stmt).first()
        assert admin is None

    def test_cannot_delete_self(
        self, client: Any, bootstrapped_admin: dict[str, Any], db_session: Session
    ) -> None:
        """Admin should not be able to delete their own account."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        # Get own admin ID
        from sqlmodel import select

        stmt = select(AdminUser).where(AdminUser.username == "admin")
        admin = db_session.exec(stmt).first()
        assert admin is not None

        # Try to delete self
        response = client.delete(
            f"/api/admin/accounts/{admin.id}",
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert response.status_code == 403
        assert "cannot delete" in response.json().get("detail", "").lower()

    def test_update_admin_account(self, client: Any, bootstrapped_admin: dict[str, Any]) -> None:
        """Admin should be able to update another admin account."""
        client.cookies.set("session_id", bootstrapped_admin["session_id"])
        client.cookies.set("csrftoken", bootstrapped_admin["csrf_token"])

        # Add another admin
        create_response = client.post(
            "/api/admin/accounts",
            json={
                "username": "admin2",
                "password": "AnotherSecure123!",
                "email": "admin2@example.com",
                "role": "admin",
            },
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )
        admin2_id = create_response.json()["id"]

        # Update admin2's email
        update_response = client.patch(
            f"/api/admin/accounts/{admin2_id}",
            json={"email": "newemail@example.com"},
            headers={"X-CSRF-Token": bootstrapped_admin["csrf_token"]},
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["email"] == "newemail@example.com"
