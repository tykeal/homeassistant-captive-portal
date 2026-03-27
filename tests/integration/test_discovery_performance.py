# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Performance test for discovery endpoint (T042).

Verifies discovery endpoint responds within acceptable latency.
"""

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.integrations.ha_client import HAClient


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


class TestDiscoveryPerformance:
    """Discovery endpoint should respond quickly even with many entities."""

    def test_discover_latency_under_1_second(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Discovery with 100 entities responds under 1 second."""
        # Generate 100 entities (50 rental, 50 other)
        entities: list[dict[str, Any]] = []
        for i in range(50):
            entities.append({
                "entity_id": f"calendar.rental_control_unit_{i}",
                "state": "on" if i % 2 == 0 else "off",
                "attributes": {
                    "friendly_name": f"Unit {i}",
                    "message": f"Guest {i}" if i % 2 == 0 else None,
                },
            })
        for i in range(50):
            entities.append({
                "entity_id": f"sensor.temperature_{i}",
                "state": str(20 + i * 0.1),
                "attributes": {"friendly_name": f"Temp {i}"},
            })

        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(return_value=entities)
        app.state.ha_client = mock

        _login(client)

        start = time.monotonic()
        resp = client.get("/api/integrations/discover")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["integrations"]) == 50
        assert elapsed < 1.0, f"Discovery took {elapsed:.2f}s, expected < 1s"

    def test_discover_with_zero_entities_is_fast(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Empty HA state list responds under 200ms."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(return_value=[])
        app.state.ha_client = mock

        _login(client)

        start = time.monotonic()
        resp = client.get("/api/integrations/discover")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.2, f"Empty discovery took {elapsed:.2f}s, expected < 200ms"
