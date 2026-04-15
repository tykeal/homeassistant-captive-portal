# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for refresh discovery endpoint and AJAX refresh (T037-T040).

Covers:
  (a) GET /api/integrations/discover returns fresh data on each call
  (b) Refresh button present in template
  (c) Loading indicator CSS class exists
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.integrations.ha_client import HAClient

# ── Fixtures ─────────────────────────────────────────────────────────

_INITIAL_STATES: list[dict[str, Any]] = [
    {
        "entity_id": "calendar.rental_control_cabin_x",
        "state": "on",
        "attributes": {
            "friendly_name": "Cabin X",
            "message": "First Guest",
            "start_time": "2025-07-01T15:00:00",
            "end_time": "2025-07-04T11:00:00",
        },
    },
]

_INITIAL_REGISTRY: list[dict[str, Any]] = [
    {"entity_id": "calendar.rental_control_cabin_x", "platform": "rental_control"},
]

_REFRESHED_REGISTRY: list[dict[str, Any]] = [
    {"entity_id": "calendar.rental_control_cabin_x", "platform": "rental_control"},
    {"entity_id": "calendar.rental_control_cabin_y", "platform": "rental_control"},
]

_REFRESHED_STATES: list[dict[str, Any]] = [
    {
        "entity_id": "calendar.rental_control_cabin_x",
        "state": "on",
        "attributes": {
            "friendly_name": "Cabin X",
            "message": "Second Guest",
            "start_time": "2025-07-05T15:00:00",
            "end_time": "2025-07-08T11:00:00",
        },
    },
    {
        "entity_id": "calendar.rental_control_cabin_y",
        "state": "off",
        "attributes": {"friendly_name": "Cabin Y"},
    },
]


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


# ── (a) Refresh returns fresh data ──────────────────────────────────


class TestRefreshEndpoint:
    """GET /api/integrations/discover returns fresh data each time."""

    def test_discover_returns_updated_data(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Consecutive discover calls reflect updated HA state."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(return_value=_INITIAL_STATES)
        mock.get_entity_registry = AsyncMock(return_value=_INITIAL_REGISTRY)
        app.state.ha_client = mock

        _login(client)

        # First call
        resp1 = client.get("/api/integrations/discover")
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["integrations"]) == 1
        assert body1["integrations"][0]["event_summary"] == "First Guest"

        # Update mock to return new data
        mock.get_all_states = AsyncMock(return_value=_REFRESHED_STATES)
        mock.get_entity_registry = AsyncMock(return_value=_REFRESHED_REGISTRY)

        # Second call (refresh)
        resp2 = client.get("/api/integrations/discover")
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["integrations"]) == 2
        assert body2["integrations"][0]["event_summary"] == "Second Guest"

    def test_discover_endpoint_is_idempotent(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """GET discover is safe to call repeatedly (idempotent)."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(return_value=_INITIAL_STATES)
        mock.get_entity_registry = AsyncMock(return_value=_INITIAL_REGISTRY)
        app.state.ha_client = mock

        _login(client)

        for _ in range(3):
            resp = client.get("/api/integrations/discover")
            assert resp.status_code == 200
            assert resp.json()["available"] is True


# ── (b) Refresh button in template ──────────────────────────────────


class TestRefreshButtonInTemplate:
    """Integrations page has a refresh discovery button."""

    def test_refresh_button_present(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Template includes a refresh/re-discover button or link."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(return_value=_INITIAL_STATES)
        mock.get_entity_registry = AsyncMock(return_value=_INITIAL_REGISTRY)
        app.state.ha_client = mock

        _login(client)
        resp = client.get("/admin/integrations/")
        assert resp.status_code == 200
        html = resp.text.lower()
        assert (
            "refresh" in html or "re-discover" in html or "rediscover" in html or "reload" in html
        )


# ── (c) Loading indicator CSS ───────────────────────────────────────


class TestLoadingIndicatorCSS:
    """Admin CSS includes loading indicator styles."""

    def test_loading_css_class_exists(self) -> None:
        """admin.css contains a loading/spinner CSS class."""
        import pathlib

        css_path = pathlib.Path("addon/src/captive_portal/web/themes/default/admin.css")
        css_content = css_path.read_text()
        assert (
            "loading" in css_content.lower()
            or "spinner" in css_content.lower()
            or "refreshing" in css_content.lower()
        )
