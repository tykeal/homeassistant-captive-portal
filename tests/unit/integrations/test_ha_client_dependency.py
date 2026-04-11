# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for get_ha_client FastAPI dependency (T012)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ha_client_created_during_lifespan_startup() -> None:
    """HAClient is instantiated during lifespan startup and stored on app.state."""
    from captive_portal.app import _make_lifespan
    from captive_portal.config.settings import AppSettings
    from captive_portal.integrations.ha_client import HAClient

    settings = MagicMock(spec=AppSettings)
    settings.ha_base_url = "http://supervisor/core/api"
    settings.ha_token = "test_token_123"
    settings.db_path = "/fake/db.sqlite"
    settings.omada_configured = False
    settings.to_log_config.return_value = {"level": "INFO"}
    settings.validate_db_path.return_value = None
    settings.log_effective.return_value = None

    lifespan = _make_lifespan(settings)

    app = MagicMock()
    app.state = MagicMock()

    with (
        patch("captive_portal.app.create_db_engine") as mock_create_engine,
        patch("captive_portal.app.init_db"),
        patch("captive_portal.app.dispose_engine"),
    ):
        mock_create_engine.return_value = MagicMock()

        async with lifespan(app):
            # Verify HAClient was stored on app.state
            assert hasattr(app.state, "ha_client")
            ha_client = app.state.ha_client
            assert isinstance(ha_client, HAClient)
            assert ha_client.base_url == "http://supervisor/core/api"
            assert ha_client.token == "test_token_123"


@pytest.mark.asyncio
async def test_ha_client_closed_during_lifespan_shutdown() -> None:
    """HAClient is closed on lifespan shutdown."""
    from captive_portal.app import _make_lifespan
    from captive_portal.config.settings import AppSettings

    settings = MagicMock(spec=AppSettings)
    settings.ha_base_url = "http://supervisor/core/api"
    settings.ha_token = "test_token_123"
    settings.db_path = "/fake/db.sqlite"
    settings.omada_configured = False
    settings.to_log_config.return_value = {"level": "INFO"}
    settings.validate_db_path.return_value = None
    settings.log_effective.return_value = None

    lifespan = _make_lifespan(settings)

    app = MagicMock()
    app.state = MagicMock()

    with (
        patch("captive_portal.app.create_db_engine") as mock_create_engine,
        patch("captive_portal.app.init_db"),
        patch("captive_portal.app.dispose_engine"),
    ):
        mock_create_engine.return_value = MagicMock()

        # Patch HAClient to track close calls
        with patch("captive_portal.app.HAClient") as MockHAClient:
            mock_ha_instance = MagicMock()
            mock_ha_instance.close = AsyncMock()
            MockHAClient.return_value = mock_ha_instance

            async with lifespan(app):
                pass  # lifespan context active

            # After lifespan exits, close should have been called
            mock_ha_instance.close.assert_awaited_once()


def test_get_ha_client_returns_instance_from_app_state() -> None:
    """get_ha_client dependency returns HAClient from request.app.state."""
    from captive_portal.integrations.ha_client import HAClient, get_ha_client

    mock_ha_client = MagicMock(spec=HAClient)

    mock_request = MagicMock()
    mock_request.app.state.ha_client = mock_ha_client

    result = get_ha_client(mock_request)

    assert result is mock_ha_client
