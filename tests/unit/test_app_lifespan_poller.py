# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for admin app lifespan HA poller wiring.

Validates that the admin app creates and starts an ``HAPoller`` on
startup and stops it cleanly on shutdown.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.integrations.ha_poller import HAPoller


class TestAdminLifespanPollerWiring:
    """Tests for HA poller lifecycle in admin app."""

    def test_ha_poller_stored_on_state(self) -> None:
        """app.state.ha_poller should be an HAPoller instance."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert hasattr(app.state, "ha_poller")
            assert isinstance(app.state.ha_poller, HAPoller)

    def test_poller_session_stored_on_state(self) -> None:
        """app.state.poller_session should exist during lifespan."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert hasattr(app.state, "poller_session")
            assert app.state.poller_session is not None

    def test_poller_task_stored_on_state(self) -> None:
        """app.state.ha_poller_task should exist during lifespan."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert hasattr(app.state, "ha_poller_task")
            assert app.state.ha_poller_task is not None

    def test_poller_shutdown_clean(self) -> None:
        """Poller should stop without errors on app shutdown."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            poller = app.state.ha_poller

        # After context exit (shutdown), poller should be stopped
        assert poller._running is False
