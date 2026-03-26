# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for health endpoints on the guest listener."""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.guest_app import create_guest_app


@pytest.fixture
def guest_app() -> FastAPI:
    """Create guest app for health testing."""
    return create_guest_app(settings=AppSettings(db_path=":memory:"))


@pytest.fixture
def guest_client(guest_app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client with lifespan (DB initialized)."""
    with TestClient(guest_app) as client:
        yield client


class TestGuestHealthEndpoint:
    """Test /api/health on the guest listener."""

    def test_health_returns_200(self, guest_client: TestClient) -> None:
        """GET /api/health returns 200 OK."""
        response = guest_client.get("/api/health")
        assert response.status_code == 200

    def test_health_response_schema(self, guest_client: TestClient) -> None:
        """Health response contains status and timestamp."""
        response = guest_client.get("/api/health")
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestGuestReadyEndpoint:
    """Test /api/ready on the guest listener."""

    def test_ready_returns_200(self, guest_client: TestClient) -> None:
        """GET /api/ready returns 200 OK with database check."""
        response = guest_client.get("/api/ready")
        assert response.status_code == 200

    def test_ready_response_schema(self, guest_client: TestClient) -> None:
        """Readiness response contains status, timestamp, and checks."""
        response = guest_client.get("/api/ready")
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert data["checks"]["database"] == "ok"


class TestGuestLiveEndpoint:
    """Test /api/live on the guest listener."""

    def test_live_returns_200(self, guest_client: TestClient) -> None:
        """GET /api/live returns 200 OK."""
        response = guest_client.get("/api/live")
        assert response.status_code == 200

    def test_live_response_schema(self, guest_client: TestClient) -> None:
        """Liveness response contains status and timestamp."""
        response = guest_client.get("/api/live")
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
