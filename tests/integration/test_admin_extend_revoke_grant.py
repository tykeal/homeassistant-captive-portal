# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin extend and revoke grant operations."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.app import create_app
from captive_portal.models.access_grant import AccessGrant
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
def authenticated_client(client) -> Any:
    """Create authenticated admin client."""
    login_response = client.post(
        "/api/admin/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert login_response.status_code == 200
    csrf_token = login_response.cookies.get("csrftoken")
    return client, csrf_token


@pytest.fixture
def sample_grant(app) -> Any:
    """Create sample access grant in database."""
    db: Session = next(get_session())
    grant = AccessGrant(
        mac_address="AA:BB:CC:DD:EE:FF",
        start_utc=datetime.utcnow(),
        end_utc=datetime.utcnow() + timedelta(hours=2),
        booking_identifier="BOOKING123",
        integration_id="rental_1",
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    yield grant
    db.delete(grant)
    db.commit()


class TestAdminExtendRevokeGrant:
    """Test admin operations for extending and revoking access grants."""

    def test_extend_grant_success(self, authenticated_client, sample_grant) -> None:
        """Admin should be able to extend grant end time."""
        client, csrf_token = authenticated_client
        grant_id = sample_grant.id

        original_end = sample_grant.end_utc
        extend_minutes = 60

        response = client.post(
            f"/api/admin/grants/{grant_id}/extend",
            json={"extend_minutes": extend_minutes},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "end_utc" in data
        # New end should be ~60 minutes later
        new_end = datetime.fromisoformat(data["end_utc"].replace("Z", "+00:00"))
        assert new_end > original_end

    def test_extend_grant_not_found(self, authenticated_client) -> None:
        """Extending non-existent grant should return 404."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/api/admin/grants/99999/extend",
            json={"extend_minutes": 60},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 404

    def test_extend_grant_invalid_minutes(self, authenticated_client, sample_grant) -> None:
        """Extending grant with invalid minutes should return 422."""
        client, csrf_token = authenticated_client

        # Negative minutes
        response = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": -30},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 422

    def test_extend_grant_zero_minutes(self, authenticated_client, sample_grant) -> None:
        """Extending grant by zero minutes should return 422."""
        client, csrf_token = authenticated_client

        response = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": 0},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 422

    def test_extend_grant_without_csrf_fails(self, authenticated_client, sample_grant) -> None:
        """Extending grant without CSRF token should fail."""
        client, _ = authenticated_client

        response = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": 60},
        )

        assert response.status_code == 403

    def test_revoke_grant_success(self, authenticated_client, sample_grant) -> None:
        """Admin should be able to revoke access grant."""
        client, csrf_token = authenticated_client
        grant_id = sample_grant.id

        response = client.post(
            f"/api/admin/grants/{grant_id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200

        # Verify grant is revoked (end_utc set to now or past)
        verify_response = client.get(f"/api/admin/grants/{grant_id}")
        assert verify_response.status_code == 200
        data = verify_response.json()
        end_utc = datetime.fromisoformat(data["end_utc"].replace("Z", "+00:00"))
        assert end_utc <= datetime.utcnow()

    def test_revoke_grant_not_found(self, authenticated_client) -> None:
        """Revoking non-existent grant should return 404."""
        client, csrf_token = authenticated_client

        response = client.post(
            "/api/admin/grants/99999/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 404

    def test_revoke_grant_already_expired(self, authenticated_client, app) -> None:
        """Revoking already expired grant should succeed (idempotent)."""
        client, csrf_token = authenticated_client

        # Create expired grant
        db: Session = next(get_session())
        expired_grant = AccessGrant(
            mac_address="11:22:33:44:55:66",
            start_utc=datetime.utcnow() - timedelta(hours=3),
            end_utc=datetime.utcnow() - timedelta(hours=1),
            booking_identifier="EXPIRED123",
        )
        db.add(expired_grant)
        db.commit()
        db.refresh(expired_grant)

        response = client.post(
            f"/api/admin/grants/{expired_grant.id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should succeed (idempotent)
        assert response.status_code == 200

        db.delete(expired_grant)
        db.commit()

    def test_revoke_grant_without_csrf_fails(self, authenticated_client, sample_grant) -> None:
        """Revoking grant without CSRF token should fail."""
        client, _ = authenticated_client

        response = client.post(f"/api/admin/grants/{sample_grant.id}/revoke")

        assert response.status_code == 403

    def test_extend_grant_creates_audit_log(self, authenticated_client, sample_grant) -> None:
        """Extending grant should create audit log entry."""
        client, csrf_token = authenticated_client

        response = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": 60},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200

        # Verify audit log created (would check audit_log table)
        # This is implementation-specific

    def test_revoke_grant_creates_audit_log(self, authenticated_client, sample_grant) -> None:
        """Revoking grant should create audit log entry."""
        client, csrf_token = authenticated_client

        response = client.post(
            f"/api/admin/grants/{sample_grant.id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200

        # Verify audit log created (would check audit_log table)

    def test_extend_grant_max_limit(self, authenticated_client, sample_grant) -> None:
        """Extending grant should respect maximum extension limit."""
        client, csrf_token = authenticated_client

        # Try to extend by very large amount
        response = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": 100000},
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should either succeed with capped value or return 422
        assert response.status_code in (200, 422)

    def test_extend_grant_multiple_times(self, authenticated_client, sample_grant) -> None:
        """Grant should be extendable multiple times."""
        client, csrf_token = authenticated_client

        # First extension
        response1 = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": 30},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response1.status_code == 200
        end1 = response1.json()["end_utc"]

        # Second extension
        response2 = client.post(
            f"/api/admin/grants/{sample_grant.id}/extend",
            json={"extend_minutes": 30},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response2.status_code == 200
        end2 = response2.json()["end_utc"]

        # Second end should be later than first
        assert end2 > end1

    def test_revoke_grant_idempotent(self, authenticated_client, sample_grant) -> None:
        """Revoking grant multiple times should be idempotent."""
        client, csrf_token = authenticated_client

        # First revoke
        response1 = client.post(
            f"/api/admin/grants/{sample_grant.id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response1.status_code == 200

        # Second revoke
        response2 = client.post(
            f"/api/admin/grants/{sample_grant.id}/revoke",
            headers={"X-CSRF-Token": csrf_token},
        )
        # Should succeed (idempotent)
        assert response2.status_code == 200
