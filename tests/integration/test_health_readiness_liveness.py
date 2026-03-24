# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0714 – Integration tests for health, readiness, and liveness endpoints.

Container probe mapping (document for ops / Helm charts):
  livenessProbe:
    httpGet:
      path: /api/live
      port: 8099
    periodSeconds: 10
  readinessProbe:
    httpGet:
      path: /api/ready
      port: 8099
    periodSeconds: 5
  startupProbe:
    httpGet:
      path: /api/health
      port: 8099
    failureThreshold: 30
    periodSeconds: 2
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHealthEndpoint:
    """Basic health check (startup probe)."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """GET /api/health must return 200."""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_status_ok(self, client: TestClient) -> None:
        """Payload includes status 'ok'."""
        data = client.get("/api/health").json()
        assert data["status"] == "ok"

    def test_health_has_timestamp(self, client: TestClient) -> None:
        """Payload includes a timestamp field."""
        data = client.get("/api/health").json()
        assert "timestamp" in data
        assert data["timestamp"] is not None


# ---------------------------------------------------------------------------
# /api/ready
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReadinessEndpoint:
    """Readiness probe – DB and dependency checks."""

    def test_ready_returns_200(self, client: TestClient) -> None:
        """GET /api/ready must return 200 when dependencies are healthy."""
        resp = client.get("/api/ready")
        assert resp.status_code == 200

    def test_ready_status_ok(self, client: TestClient) -> None:
        """Payload status should be 'ok' when DB is reachable."""
        data = client.get("/api/ready").json()
        assert data["status"] == "ok"

    def test_ready_checks_database(self, client: TestClient) -> None:
        """Readiness payload includes a 'database' check."""
        data = client.get("/api/ready").json()
        assert "checks" in data
        assert data["checks"]["database"] == "ok"

    def test_ready_has_timestamp(self, client: TestClient) -> None:
        """Payload includes a timestamp."""
        data = client.get("/api/ready").json()
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# /api/live
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLivenessEndpoint:
    """Liveness probe – basic process-alive check."""

    def test_live_returns_200(self, client: TestClient) -> None:
        """GET /api/live must return 200."""
        resp = client.get("/api/live")
        assert resp.status_code == 200

    def test_live_status_ok(self, client: TestClient) -> None:
        """Payload includes status 'ok'."""
        data = client.get("/api/live").json()
        assert data["status"] == "ok"

    def test_live_has_timestamp(self, client: TestClient) -> None:
        """Payload includes a timestamp field."""
        data = client.get("/api/live").json()
        assert "timestamp" in data
        assert data["timestamp"] is not None


# ---------------------------------------------------------------------------
# Cross-endpoint guarantees
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProbeConsistency:
    """All three probe endpoints share common contract guarantees."""

    _PROBES = ["/api/health", "/api/ready", "/api/live"]

    def test_all_probes_return_json(self, client: TestClient) -> None:
        """Every probe returns valid JSON."""
        for path in self._PROBES:
            resp = client.get(path)
            assert resp.status_code == 200
            resp.json()  # will raise if not valid JSON

    def test_all_probes_have_status_field(self, client: TestClient) -> None:
        """Every probe payload contains a 'status' key."""
        for path in self._PROBES:
            data = client.get(path).json()
            assert "status" in data, f"{path} missing 'status'"

    def test_all_probes_have_timestamp(self, client: TestClient) -> None:
        """Every probe payload contains a 'timestamp' key."""
        for path in self._PROBES:
            data = client.get(path).json()
            assert "timestamp" in data, f"{path} missing 'timestamp'"
