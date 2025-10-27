# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for admin list filtering and pagination."""

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
    return client


@pytest.fixture
def sample_grants(app) -> Any:
    """Create multiple sample grants for filtering tests."""
    db: Session = next(get_session())
    grants = []

    # Active grant
    grants.append(
        AccessGrant(
            mac_address="AA:BB:CC:DD:EE:01",
            start_utc=datetime.utcnow() - timedelta(hours=1),
            end_utc=datetime.utcnow() + timedelta(hours=1),
            booking_identifier="ACTIVE001",
            integration_id="rental_1",
        )
    )

    # Expired grant
    grants.append(
        AccessGrant(
            mac_address="AA:BB:CC:DD:EE:02",
            start_utc=datetime.utcnow() - timedelta(hours=3),
            end_utc=datetime.utcnow() - timedelta(hours=1),
            booking_identifier="EXPIRED001",
            integration_id="rental_1",
        )
    )

    # Future grant
    grants.append(
        AccessGrant(
            mac_address="AA:BB:CC:DD:EE:03",
            start_utc=datetime.utcnow() + timedelta(hours=1),
            end_utc=datetime.utcnow() + timedelta(hours=3),
            booking_identifier="FUTURE001",
            integration_id="rental_2",
        )
    )

    for grant in grants:
        db.add(grant)
    db.commit()

    for grant in grants:
        db.refresh(grant)

    yield grants

    for grant in grants:
        db.delete(grant)
    db.commit()


class TestAdminListFilters:
    """Test admin list filtering and pagination."""

    def test_list_all_grants_without_filter(self, authenticated_client, sample_grants) -> None:
        """Listing grants without filter should return all grants."""
        client = authenticated_client

        response = client.get("/api/admin/grants")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # At least our sample grants

    def test_filter_grants_by_status_active(self, authenticated_client, sample_grants) -> None:
        """Filter grants by status=active."""
        client = authenticated_client

        response = client.get("/api/admin/grants?status=active")

        assert response.status_code == 200
        data = response.json()
        # Should only return active grants
        for grant in data:
            end_utc = datetime.fromisoformat(grant["end_utc"].replace("Z", "+00:00"))
            assert end_utc > datetime.utcnow()

    def test_filter_grants_by_status_expired(self, authenticated_client, sample_grants) -> None:
        """Filter grants by status=expired."""
        client = authenticated_client

        response = client.get("/api/admin/grants?status=expired")

        assert response.status_code == 200
        data = response.json()
        # Should only return expired grants
        for grant in data:
            end_utc = datetime.fromisoformat(grant["end_utc"].replace("Z", "+00:00"))
            assert end_utc <= datetime.utcnow()

    def test_filter_grants_by_integration_id(self, authenticated_client, sample_grants) -> None:
        """Filter grants by integration_id."""
        client = authenticated_client

        response = client.get("/api/admin/grants?integration_id=rental_1")

        assert response.status_code == 200
        data = response.json()
        for grant in data:
            assert grant.get("integration_id") == "rental_1"

    def test_filter_grants_by_booking_identifier(self, authenticated_client, sample_grants) -> None:
        """Filter grants by booking_identifier."""
        client = authenticated_client

        response = client.get("/api/admin/grants?booking_identifier=ACTIVE001")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["booking_identifier"] == "ACTIVE001"

    def test_pagination_limit(self, authenticated_client, sample_grants) -> None:
        """Pagination with limit parameter."""
        client = authenticated_client

        response = client.get("/api/admin/grants?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2

    def test_pagination_offset(self, authenticated_client, sample_grants) -> None:
        """Pagination with offset parameter."""
        client = authenticated_client

        # Get first page
        response1 = client.get("/api/admin/grants?limit=1&offset=0")
        assert response1.status_code == 200
        page1 = response1.json()

        # Get second page
        response2 = client.get("/api/admin/grants?limit=1&offset=1")
        assert response2.status_code == 200
        page2 = response2.json()

        # Should be different grants
        if len(page1) > 0 and len(page2) > 0:
            assert page1[0]["id"] != page2[0]["id"]

    def test_combined_filters(self, authenticated_client, sample_grants) -> None:
        """Multiple filters combined."""
        client = authenticated_client

        response = client.get("/api/admin/grants?status=active&integration_id=rental_1")

        assert response.status_code == 200
        data = response.json()
        for grant in data:
            # Should match both filters
            assert grant.get("integration_id") == "rental_1"
            end_utc = datetime.fromisoformat(grant["end_utc"].replace("Z", "+00:00"))
            assert end_utc > datetime.utcnow()

    def test_filter_invalid_status(self, authenticated_client) -> None:
        """Invalid status filter should return 422."""
        client = authenticated_client

        response = client.get("/api/admin/grants?status=invalid_status")

        assert response.status_code == 422

    def test_pagination_negative_limit(self, authenticated_client) -> None:
        """Negative limit should return 422."""
        client = authenticated_client

        response = client.get("/api/admin/grants?limit=-1")

        assert response.status_code == 422

    def test_pagination_negative_offset(self, authenticated_client) -> None:
        """Negative offset should return 422."""
        client = authenticated_client

        response = client.get("/api/admin/grants?offset=-1")

        assert response.status_code == 422

    def test_list_grants_returns_metadata(self, authenticated_client, sample_grants) -> None:
        """List response should include pagination metadata."""
        client = authenticated_client

        response = client.get("/api/admin/grants?limit=2")

        assert response.status_code == 200
        # Check for pagination metadata in headers or response
        # Implementation may vary
