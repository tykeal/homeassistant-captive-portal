# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests for the integrations auto-detection feature (T041).

End-to-end user stories verifying the complete discovery → configure flow.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_errors import HAConnectionError
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


_CABIN_STATES: list[dict[str, Any]] = [
    {
        "entity_id": "calendar.rental_control_cabin_a",
        "state": "on",
        "attributes": {
            "friendly_name": "Cabin A Calendar",
            "message": "Guest Smith",
            "start_time": "2025-07-01T15:00:00",
            "end_time": "2025-07-05T11:00:00",
        },
    },
    {
        "entity_id": "calendar.rental_control_cabin_b",
        "state": "off",
        "attributes": {"friendly_name": "Cabin B Calendar"},
    },
    {
        "entity_id": "sensor.temperature",
        "state": "22.5",
        "attributes": {"friendly_name": "Temperature Sensor"},
    },
]


@pytest.fixture()
def _mock_ha_cabins(app: FastAPI) -> MagicMock:
    """Attach mock HAClient returning cabin entities."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(return_value=_CABIN_STATES)
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


class TestAcceptanceDiscoverAndConfigure:
    """Full flow: discover entities → configure integration → verify."""

    def test_discover_then_configure_integration(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
        _mock_ha_cabins: MagicMock,
    ) -> None:
        """Admin discovers HA entities and configures one via dropdown."""
        csrf = _login(client)

        # Step 1: View integrations page — sees discovered entities
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        assert "calendar.rental_control_cabin_a" in html
        assert "calendar.rental_control_cabin_b" in html
        assert "sensor.temperature" not in html

        # Step 2: Select from dropdown and save
        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "calendar.rental_control_cabin_a",
                "identifier_attr": "slot_code",
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Step 3: Verify config was created
        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "calendar.rental_control_cabin_a"
            )
        ).first()
        assert row is not None
        assert row.identifier_attr == IdentifierAttr.SLOT_CODE

    def test_discover_api_then_verify_json_structure(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_cabins: MagicMock,
    ) -> None:
        """API discover returns well-structured DiscoveryResult JSON."""
        _login(client)

        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200
        body = resp.json()

        # Top-level fields
        assert body["available"] is True
        assert isinstance(body["integrations"], list)
        assert body["error_message"] is None

        # Only rental control entities
        entity_ids = [i["entity_id"] for i in body["integrations"]]
        assert "calendar.rental_control_cabin_a" in entity_ids
        assert "calendar.rental_control_cabin_b" in entity_ids
        assert "sensor.temperature" not in entity_ids

        # Integration fields
        cabin_a = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_cabin_a"
        )
        assert cabin_a["friendly_name"] == "Cabin A Calendar"
        assert cabin_a["state"] == "on"
        assert cabin_a["state_display"] == "Active booking"
        assert cabin_a["event_summary"] == "Guest Smith"
        assert cabin_a["already_configured"] is False

    def test_configure_then_mark_already_configured(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
        _mock_ha_cabins: MagicMock,
    ) -> None:
        """After saving, re-discover marks entity as already_configured."""
        csrf = _login(client)

        # Save integration
        client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "calendar.rental_control_cabin_a",
                "identifier_attr": "slot_code",
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        # Re-discover
        resp = client.get("/api/integrations/discover")
        body = resp.json()
        cabin_a = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_cabin_a"
        )
        assert cabin_a["already_configured"] is True

        cabin_b = next(
            i for i in body["integrations"] if i["entity_id"] == "calendar.rental_control_cabin_b"
        )
        assert cabin_b["already_configured"] is False


class TestAcceptanceFallbackFlow:
    """When HA is down, admin can still manually configure integrations."""

    def test_ha_down_manual_configuration(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Admin can configure integrations manually when HA is unreachable."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(
            side_effect=HAConnectionError(
                user_message="Cannot connect to Home Assistant",
                detail="connection refused",
            )
        )
        app.state.ha_client = mock

        csrf = _login(client)

        # Page still loads
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200

        # Manual configuration works
        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "manual_fallback_test",
                "identifier_attr": "last_four",
                "checkout_grace_minutes": "10",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "manual_fallback_test"
            )
        ).first()
        assert row is not None
        assert row.identifier_attr == IdentifierAttr.LAST_FOUR
