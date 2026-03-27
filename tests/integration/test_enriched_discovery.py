# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for enriched discovery fields (T024/T025).

Verifies that DiscoveredIntegration includes:
  - next_event_summary (from calendar message attribute)
  - next_checkin_date (from calendar start_time attribute)
  - state_display (human-readable state label)
  - state extraction from raw HA entity data
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.integrations.ha_client import HAClient

# ── Test data ────────────────────────────────────────────────────────

_ENRICHED_STATES: list[dict[str, Any]] = [
    {
        "entity_id": "calendar.rental_control_unit_a",
        "state": "on",
        "attributes": {
            "friendly_name": "Unit A Calendar",
            "message": "Guest Johnson",
            "start_time": "2025-07-10T15:00:00",
            "end_time": "2025-07-14T11:00:00",
        },
    },
    {
        "entity_id": "calendar.rental_control_unit_b",
        "state": "off",
        "attributes": {
            "friendly_name": "Unit B Calendar",
        },
    },
    {
        "entity_id": "calendar.rental_control_unit_c",
        "state": "unavailable",
        "attributes": {
            "friendly_name": "Unit C Calendar",
        },
    },
]


@pytest.fixture()
def _mock_ha_enriched(app: FastAPI) -> MagicMock:
    """Attach a mock HAClient with enriched entity data."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(return_value=_ENRICHED_STATES)
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


# ── Enriched field tests ─────────────────────────────────────────────


class TestEnrichedDiscoveryFields:
    """DiscoveredIntegration carries enriched fields from HA entity state."""

    def test_next_event_summary_populated(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """Active booking entity has next_event_summary from message attr."""
        _login(client)
        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200

        body = resp.json()
        unit_a = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_unit_a"
        )
        assert unit_a["event_summary"] == "Guest Johnson"

    def test_next_checkin_date_populated(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """Active booking entity has event_start from start_time attr."""
        _login(client)
        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200

        body = resp.json()
        unit_a = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_unit_a"
        )
        assert unit_a["event_start"] == "2025-07-10T15:00:00"

    def test_no_event_fields_when_off(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """Inactive entity has null event fields."""
        _login(client)
        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200

        body = resp.json()
        unit_b = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_unit_b"
        )
        assert unit_b["event_summary"] is None
        assert unit_b["event_start"] is None


# ── State display tests ──────────────────────────────────────────────


class TestStateDisplay:
    """DiscoveredIntegration.state_display maps state to human label."""

    def test_state_on_display(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """State 'on' maps to 'Active booking'."""
        _login(client)
        resp = client.get("/api/integrations/discover")
        body = resp.json()
        unit_a = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_unit_a"
        )
        assert unit_a["state_display"] == "Active booking"

    def test_state_off_display(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """State 'off' maps to 'No active bookings'."""
        _login(client)
        resp = client.get("/api/integrations/discover")
        body = resp.json()
        unit_b = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_unit_b"
        )
        assert unit_b["state_display"] == "No active bookings"

    def test_state_unavailable_display(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """State 'unavailable' maps to 'Unavailable'."""
        _login(client)
        resp = client.get("/api/integrations/discover")
        body = resp.json()
        unit_c = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_unit_c"
        )
        assert unit_c["state_display"] == "Unavailable"


# ── Template rendering with enriched data ────────────────────────────


class TestEnrichedTemplateRendering:
    """Integrations page shows state badges and event info."""

    def test_state_badge_in_html(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """Discovered integration dropdown shows state display text."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        assert "Active booking" in html or "active booking" in html.lower()

    def test_event_summary_in_html(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_enriched: MagicMock,
    ) -> None:
        """Event summary appears in HTML when available."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        assert "Guest Johnson" in html
