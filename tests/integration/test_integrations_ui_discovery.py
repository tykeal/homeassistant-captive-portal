# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for list_integrations with discovery context (T016).

The ``GET /admin/integrations/`` template context must include a
``discovery_result`` (DiscoveryResult) so the UI can show a dropdown of
discovered HA calendar entities.

These tests will **fail** until ``list_integrations`` calls the
discovery service and passes the result to the template.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_errors import HAConnectionError

# ── Test data ────────────────────────────────────────────────────────

_HA_STATES_WITH_RENTALS: list[dict[str, Any]] = [
    {
        "entity_id": "calendar.rental_control_unit_1",
        "state": "on",
        "attributes": {
            "friendly_name": "Unit 1 Calendar",
            "message": "Booking A",
            "start_time": "2025-07-01T15:00:00",
            "end_time": "2025-07-04T11:00:00",
        },
    },
    {
        "entity_id": "calendar.rental_control_unit_2",
        "state": "off",
        "attributes": {"friendly_name": "Unit 2 Calendar"},
    },
    {
        "entity_id": "sensor.temperature",
        "state": "22.5",
        "attributes": {"friendly_name": "Temperature Sensor"},
    },
]


_HA_REGISTRY: list[dict[str, Any]] = [
    {"entity_id": "calendar.rental_control_unit_1", "platform": "rental_control"},
    {"entity_id": "calendar.rental_control_unit_2", "platform": "rental_control"},
]


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def _mock_ha_available(app: FastAPI) -> MagicMock:
    """Attach a mock HAClient returning rental entities successfully."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(return_value=_HA_STATES_WITH_RENTALS)
    mock.get_entity_registry = AsyncMock(return_value=_HA_REGISTRY)
    app.state.ha_client = mock
    return mock


@pytest.fixture()
def _mock_ha_unavailable(app: FastAPI) -> MagicMock:
    """Attach a mock HAClient that raises HAConnectionError."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(
        side_effect=HAConnectionError(
            user_message="Cannot connect to Home Assistant",
            detail="connection refused",
        )
    )
    mock.get_entity_registry = AsyncMock(return_value=[])
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


# ── HA available: template receives discovery_result ─────────────────


class TestDiscoveryContextAvailable:
    """When HA is reachable the integrations page shows discoveries."""

    def test_page_returns_200_when_ha_available(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """GET /admin/integrations/ should succeed with discovery."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200

    def test_html_contains_discovered_entity_dropdown(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Rendered HTML should contain discovered entity IDs."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text
        assert "calendar.rental_control_unit_1" in html, (
            "Expected discovered entity_id in rendered HTML"
        )
        assert "calendar.rental_control_unit_2" in html, (
            "Expected second discovered entity_id in rendered HTML"
        )

    def test_html_contains_select_element_for_discovery(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Friendly names from discovery should appear in the HTML."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text.lower()
        assert "unit 1 calendar" in html or "unit_1" in html, (
            "Expected friendly name or entity ID from discovery"
        )

    def test_non_rental_entities_excluded_from_html(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Non-rental-control entities must not appear in the HTML."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text
        assert "sensor.temperature" not in html, (
            "Non-rental entity should not appear on integrations page"
        )


# ── HA unavailable: template receives error context ──────────────────


class TestDiscoveryContextUnavailable:
    """When HA is unreachable the page still loads with error context."""

    def test_page_returns_200_when_ha_unavailable(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """Page should still load (200) even if HA discovery fails."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200

    def test_html_shows_connection_error_message(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """Rendered HTML should display a user-friendly error message."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text.lower()
        assert "cannot connect" in html or "unavailable" in html or "error" in html, (
            "Expected an error message when HA is unreachable"
        )

    def test_no_discovery_dropdown_when_ha_unavailable(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """No discovered entity dropdown when HA is unreachable."""
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text
        assert "calendar.rental_control_" not in html, (
            "No rental entities should appear when HA is unreachable"
        )


# ── Verify discovery_result is passed to template ────────────────────


class TestDiscoveryResultInContext:
    """Verify the template context includes a DiscoveryResult object."""

    def test_discovery_result_available_true_in_context(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_available: MagicMock,
    ) -> None:
        """Template context must contain discovery_result available=True.

        We verify by checking that the HTML output reflects discovery
        data, which can only happen if discovery_result is in context.
        """
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text
        assert "rental_control_unit_1" in html, (
            "discovery_result not propagated to template context"
        )

    def test_discovery_result_available_false_in_context(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """Template context must contain discovery_result available=False.

        When HA is down, the page should indicate the error. The
        presence of an error message proves discovery_result was passed.
        """
        _login(client)

        resp = client.get("/admin/integrations/")

        assert resp.status_code == 200
        html = resp.text
        assert "cannot connect" in html.lower() or "discovery" in html.lower(), (
            "discovery_result error not reflected in template output"
        )
