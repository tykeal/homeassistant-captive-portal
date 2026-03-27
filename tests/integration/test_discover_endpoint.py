# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for GET /api/integrations/discover endpoint (T015).

The discover endpoint should:
  (a) return DiscoveryResult JSON with available=true for authenticated
      admins
  (b) reject unauthenticated requests with 401/403
  (c) return DiscoveryResult with available=false when HA is unreachable
  (d) never leak tokens or internal URLs in the response body

These tests will **fail** until the discover endpoint is implemented.
"""

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_errors import HAConnectionError

# ── Fixtures ─────────────────────────────────────────────────────────

DISCOVER_URL = "/api/integrations/discover"

_RENTAL_STATES: list[dict[str, Any]] = [
    {
        "entity_id": "calendar.rental_control_cabin_a",
        "state": "on",
        "attributes": {
            "friendly_name": "Cabin A",
            "message": "Guest Smith",
            "start_time": "2025-06-01T14:00:00",
            "end_time": "2025-06-05T11:00:00",
        },
    },
    {
        "entity_id": "calendar.rental_control_cabin_b",
        "state": "off",
        "attributes": {"friendly_name": "Cabin B"},
    },
    {
        "entity_id": "light.kitchen",
        "state": "on",
        "attributes": {"friendly_name": "Kitchen Light"},
    },
]


@pytest.fixture()
def _mock_ha_available(app: FastAPI) -> MagicMock:
    """Attach a mock HAClient that returns rental control entities."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(return_value=_RENTAL_STATES)
    app.state.ha_client = mock
    return mock


@pytest.fixture()
def _mock_ha_unreachable(app: FastAPI) -> MagicMock:
    """Attach a mock HAClient that raises HAConnectionError."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(
        side_effect=HAConnectionError(
            user_message="Cannot connect to Home Assistant",
            detail=("http://supervisor:8123/api/states — connection refused"),
        )
    )
    app.state.ha_client = mock
    return mock


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


# ── (a) Authenticated admin receives DiscoveryResult ─────────────────


class TestDiscoverAuthenticated:
    """Authenticated admin should receive a valid DiscoveryResult."""

    def test_discover_returns_200_with_discovery_result(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """GET /api/integrations/discover returns DiscoveryResult JSON."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["available"] is True
        assert isinstance(body["integrations"], list)

    def test_discover_filters_rental_control_entities(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Only calendar.rental_control_* entities appear in result."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        assert resp.status_code == 200
        body = resp.json()
        entity_ids = [i["entity_id"] for i in body["integrations"]]
        assert "calendar.rental_control_cabin_a" in entity_ids
        assert "calendar.rental_control_cabin_b" in entity_ids
        assert "light.kitchen" not in entity_ids

    def test_discover_includes_friendly_name_and_state(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Each discovered integration carries friendly_name and state."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        assert resp.status_code == 200
        cabin_a = next(
            i
            for i in resp.json()["integrations"]
            if i["entity_id"] == "calendar.rental_control_cabin_a"
        )
        assert cabin_a["friendly_name"] == "Cabin A"
        assert cabin_a["state"] == "on"


# ── (b) Unauthenticated request ─────────────────────────────────────


class TestDiscoverUnauthenticated:
    """Unauthenticated requests must be rejected."""

    def test_unauthenticated_returns_401_or_403(
        self,
        client: TestClient,
        _mock_ha_available: MagicMock,
    ) -> None:
        """GET /api/integrations/discover without session -> 401/403."""
        resp = client.get(DISCOVER_URL)

        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


# ── (c) HA unreachable → available=false ─────────────────────────────


class TestDiscoverHAUnreachable:
    """When HA is down, the endpoint still returns 200 with error info."""

    def test_unreachable_returns_200_with_available_false(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unreachable: MagicMock,
    ) -> None:
        """HA down -> 200 + DiscoveryResult(available=False)."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        assert resp.status_code == 200, f"Expected 200 even on HA failure, got {resp.status_code}"
        body = resp.json()
        assert body["available"] is False

    def test_unreachable_includes_error_message(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unreachable: MagicMock,
    ) -> None:
        """Error response carries a safe error_message string."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["error_message"] is not None
        assert isinstance(body["error_message"], str)
        assert len(body["error_message"]) > 0

    def test_unreachable_includes_error_category(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unreachable: MagicMock,
    ) -> None:
        """Error response carries error_category (e.g. 'connection')."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["error_category"] is not None
        assert body["error_category"] in (
            "connection",
            "auth",
            "timeout",
            "server_error",
        )


# ── (d) No secrets in response ──────────────────────────────────────


class TestDiscoverNoSecretsLeaked:
    """Response body must never contain tokens or internal URLs."""

    _SENSITIVE_PATTERNS = [
        re.compile(r"Bearer\s+\S+", re.IGNORECASE),
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ"),  # JWT-like
        re.compile(r"http://supervisor", re.IGNORECASE),
        re.compile(r"http://hassio", re.IGNORECASE),
        re.compile(r"http://localhost:\d+/api", re.IGNORECASE),
    ]

    def test_successful_response_has_no_secrets(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Successful discovery response body has no sensitive data."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        body_text = resp.text
        for pattern in self._SENSITIVE_PATTERNS:
            assert not pattern.search(body_text), (
                f"Response body matches sensitive pattern: {pattern.pattern}"
            )

    def test_error_response_has_no_secrets(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unreachable: MagicMock,
    ) -> None:
        """Error discovery response has no internal URLs or tokens."""
        _login(client)

        resp = client.get(DISCOVER_URL)

        body_text = resp.text
        for pattern in self._SENSITIVE_PATTERNS:
            assert not pattern.search(body_text), (
                f"Response body matches sensitive pattern: {pattern.pattern}"
            )
