# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for fallback behavior, empty state, and manual save path (T030-T036).

Covers:
  (a) Fallback rendering when HA is unavailable — manual input + error banner
  (b) Zero integrations empty state display
  (c) Manual text input save path creates row correctly
  (d) Notification banner styling presence
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


# ── Fixtures ─────────────────────────────────────────────────────────


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
    app.state.ha_client = mock
    return mock


@pytest.fixture()
def _mock_ha_empty(app: FastAPI) -> MagicMock:
    """Attach a mock HAClient returning no rental control entities."""
    mock = MagicMock(spec=HAClient)
    mock.get_all_states = AsyncMock(return_value=[
        {
            "entity_id": "sensor.temperature",
            "state": "22.5",
            "attributes": {"friendly_name": "Temperature Sensor"},
        },
    ])
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


# ── (a) Fallback rendering ──────────────────────────────────────────


class TestFallbackRendering:
    """When HA is unavailable, template shows manual input + error banner."""

    def test_error_banner_shown(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """Page shows an error notification when HA is down."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text.lower()
        assert "discovery unavailable" in html or "cannot connect" in html

    def test_manual_input_shown_when_ha_unavailable(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """Page shows text input for integration_id when HA is down."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        assert 'name="integration_id"' in html
        assert '<input' in html

    def test_no_dropdown_when_ha_unavailable(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """No <select> dropdown for integration_id when HA is down."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        # The integration_id should be a text input, not a select
        assert 'id="integration_id"' in html
        # Verify no dropdown options with rental_control entities
        assert "calendar.rental_control_" not in html


# ── (b) Empty state ─────────────────────────────────────────────────


class TestEmptyState:
    """Zero integrations configured shows empty state messaging."""

    def test_empty_state_message_shown(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_empty: MagicMock,
    ) -> None:
        """Page shows empty state message when no integrations configured."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text.lower()
        assert "no integrations configured" in html or "empty" in html

    def test_empty_discovery_shows_manual_input(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_empty: MagicMock,
    ) -> None:
        """When discovery finds no rental entities, manual input is shown."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        assert 'name="integration_id"' in html

    def test_no_rental_discovery_message(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_empty: MagicMock,
    ) -> None:
        """When HA is available but no rental entities, show informative text."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text.lower()
        assert "no rental control" in html or "no integrations" in html


# ── (c) Manual save path ────────────────────────────────────────────


class TestManualSavePath:
    """Manual text input save path creates correct config row."""

    def test_manual_save_creates_row(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Typing integration_id manually creates a valid config row."""
        csrf = _login(client)
        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "manual_entry_test",
                "identifier_attr": "last_four",
                "checkout_grace_minutes": "5",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "manual_entry_test"
            )
        ).first()
        assert row is not None
        assert row.identifier_attr == IdentifierAttr.LAST_FOUR
        assert row.checkout_grace_minutes == 5

    def test_manual_save_with_legacy_auth_attribute(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Legacy auth_attribute form field creates row correctly."""
        csrf = _login(client)
        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "legacy_manual_test",
                "auth_attribute": "slot_name",
                "checkout_grace_minutes": "10",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "legacy_manual_test"
            )
        ).first()
        assert row is not None
        assert row.identifier_attr == IdentifierAttr.SLOT_NAME


# ── (d) Notification banner CSS ─────────────────────────────────────


class TestNotificationBannerCSS:
    """Notification banner has correct CSS classes."""

    def test_error_banner_has_alert_class(
        self,
        client: TestClient,
        admin_user: Any,
        _mock_ha_unavailable: MagicMock,
    ) -> None:
        """Error banner uses alert-error CSS class."""
        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text
        assert "alert-error" in html or "alert alert-error" in html
