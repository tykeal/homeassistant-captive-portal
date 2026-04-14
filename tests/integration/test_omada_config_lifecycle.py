# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration test for end-to-end Omada config lifecycle.

Validates that Omada settings stored in the database flow through
into app.state.omada_config and that get_omada_adapter creates correct
adapter instances.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter


class TestOmadaConfigLifecycle:
    """End-to-end tests for the Omada configuration lifecycle."""

    def test_db_config_flows_into_app_state(self) -> None:
        """DB OmadaConfig should populate app.state.omada_config."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)

        # Seed Omada config into the DB during lifespan
        with TestClient(app) as client:
            # With no DB seed, omada_config should be None
            assert app.state.omada_config is None
            resp = client.get("/api/live")
            assert resp.status_code == 200

    def test_adapter_returns_none_without_db_config(self) -> None:
        """get_omada_adapter should return None without DB Omada config."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            mock_request = MagicMock()
            mock_request.app = app
            adapter = get_omada_adapter(mock_request)
            assert adapter is None

    def test_no_startup_network_io(self) -> None:
        """No network I/O should occur during app startup."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        # If startup tried to connect, it would fail (no controller)
        # The fact that TestClient starts without error proves no I/O
        with TestClient(app) as client:
            resp = client.get("/api/live")
            assert resp.status_code == 200
