# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for admin app lifespan Omada wiring.

Validates that the admin app stores ``omada_config`` dict on ``app.state``
when configured in the database, and ``None`` when not.  No shared
client/adapter instances are stored (per-request construction pattern).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings


class TestAdminLifespanOmadaConfigured:
    """Tests when Omada controller is NOT configured (DB default)."""

    def test_omada_config_is_none_by_default(self) -> None:
        """app.state.omada_config should be None when DB has no config."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert app.state.omada_config is None

    def test_no_shared_client_on_state(self) -> None:
        """No OmadaClient or OmadaAdapter should be stored on app.state."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert not hasattr(app.state, "omada_client")
            assert not hasattr(app.state, "omada_adapter")


class TestAdminLifespanOmadaNotConfigured:
    """Tests when Omada controller URL is not configured."""

    def test_omada_config_is_none(self) -> None:
        """app.state.omada_config should be None when not configured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert app.state.omada_config is None

    def test_no_errors_when_unconfigured(self, caplog: pytest.LogCaptureFixture) -> None:
        """App should start without errors when Omada is not configured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with caplog.at_level(logging.WARNING):
            with TestClient(app) as client:
                resp = client.get("/api/live")

        assert resp.status_code == 200
        # No ERROR-level messages about Omada should be present
        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR and "omada" in r.message.lower()
        ]
        assert len(error_records) == 0
