# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration test for graceful degradation without Omada config.

Validates that the app starts cleanly and functions normally when
no Omada controller is configured in the database.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter


class TestGracefulDegradation:
    """Tests for graceful degradation when Omada is not configured."""

    def test_admin_app_starts_without_omada(self) -> None:
        """Admin app should start without errors when Omada is not configured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app) as client:
            resp = client.get("/api/live")
            assert resp.status_code == 200

        assert app.state.omada_config is None

    def test_guest_app_starts_without_omada(self) -> None:
        """Guest app should start without errors when Omada is not configured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.guest_app import create_guest_app

        app = create_guest_app(settings=settings)
        with TestClient(app) as client:
            resp = client.get("/api/live")
            assert resp.status_code == 200

        assert app.state.omada_config is None

    def test_adapter_returns_none_when_unconfigured(self) -> None:
        """get_omada_adapter should return None without Omada config."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app
        from unittest.mock import MagicMock

        app = create_app(settings=settings)
        with TestClient(app):
            mock_request = MagicMock()
            mock_request.app = app
            adapter = get_omada_adapter(mock_request)
            assert adapter is None

    def test_no_error_logs_when_unconfigured(self, caplog: pytest.LogCaptureFixture) -> None:
        """No error logs about Omada should appear when unconfigured."""
        settings = AppSettings(db_path=":memory:")
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with caplog.at_level(logging.WARNING):
            with TestClient(app):
                pass

        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR and "omada" in r.message.lower()
        ]
        assert len(error_records) == 0
