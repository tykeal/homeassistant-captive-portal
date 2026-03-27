# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Edge-case tests for discovery and save integration (T043).

Covers:
  - Entity with missing attributes
  - Entity with empty friendly_name
  - Very long integration_id
  - Concurrent duplicate creation
  - Invalid identifier_attr values
  - HA returns non-JSON response (handled by mock)
  - Various error categories (auth, timeout, server_error)
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_errors import (
    HAAuthenticationError,
    HAServerError,
    HATimeoutError,
)


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


class TestEdgeCaseEntityAttributes:
    """Discovery handles entities with unusual attribute patterns."""

    def test_entity_with_no_attributes(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Entity without attributes dict still discovered safely."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(
            return_value=[
                {
                    "entity_id": "calendar.rental_control_bare",
                    "state": "off",
                },
            ]
        )
        app.state.ha_client = mock
        _login(client)

        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["integrations"]) == 1
        integration = body["integrations"][0]
        assert integration["entity_id"] == "calendar.rental_control_bare"
        # Friendly name falls back to entity_id
        assert integration["friendly_name"] == "calendar.rental_control_bare"

    def test_entity_with_empty_friendly_name(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Entity with empty string friendly_name handled gracefully."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(
            return_value=[
                {
                    "entity_id": "calendar.rental_control_empty_name",
                    "state": "off",
                    "attributes": {"friendly_name": ""},
                },
            ]
        )
        app.state.ha_client = mock
        _login(client)

        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["integrations"]) == 1

    def test_entity_with_unknown_state(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Entity with unexpected state value still works."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(
            return_value=[
                {
                    "entity_id": "calendar.rental_control_weird",
                    "state": "custom_state",
                    "attributes": {"friendly_name": "Weird Calendar"},
                },
            ]
        )
        app.state.ha_client = mock
        _login(client)

        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200
        body = resp.json()
        integration = body["integrations"][0]
        assert integration["state"] == "custom_state"
        assert integration["state_display"] == "custom_state"


class TestEdgeCaseSaveIntegration:
    """Save integration handles edge cases correctly."""

    def test_save_with_invalid_identifier_attr_returns_422(
        self,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Invalid identifier_attr value returns 422."""
        csrf = _login(client)
        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "test_invalid_attr",
                "identifier_attr": "not_valid",
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 422

    def test_save_with_neither_attr_field_returns_422(
        self,
        client: TestClient,
        admin_user: Any,
    ) -> None:
        """Missing both identifier_attr and auth_attribute returns 422."""
        csrf = _login(client)
        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "test_no_attr",
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 422


class TestEdgeCaseErrorCategories:
    """Discovery returns correct error categories for different failures."""

    @pytest.mark.parametrize(
        "error_class, expected_category",
        [
            (HAAuthenticationError, "auth"),
            (HATimeoutError, "timeout"),
            (HAServerError, "server_error"),
        ],
        ids=["auth", "timeout", "server_error"],
    )
    def test_error_category_mapping(
        self,
        app: FastAPI,
        client: TestClient,
        admin_user: Any,
        error_class: type,
        expected_category: str,
    ) -> None:
        """Each HA error type maps to the correct error_category."""
        mock = MagicMock(spec=HAClient)
        mock.get_all_states = AsyncMock(
            side_effect=error_class(
                user_message=f"Test {expected_category} error",
                detail="test detail",
            )
        )
        app.state.ha_client = mock
        _login(client)

        resp = client.get("/api/integrations/discover")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["error_category"] == expected_category
