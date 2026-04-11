# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for admin app lifespan Omada wiring.

Validates that the admin app stores ``omada_config`` dict on ``app.state``
when configured, and ``None`` when not. No shared client/adapter instances
are stored (per-request construction pattern).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings


class TestAdminLifespanOmadaConfigured:
    """Tests when Omada controller URL is configured."""

    def test_omada_config_dict_on_state(self) -> None:
        """app.state.omada_config should be a dict with expected keys."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="aabbccdd1122334455667788",
            omada_username="user1",
            omada_password="pass1",
            omada_verify_ssl=False,
            omada_site_name="MySite",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            config = app.state.omada_config
            assert config is not None
            assert isinstance(config, dict)
            assert config["base_url"] == "https://ctrl.local:8043"
            assert config["controller_id"] == "aabbccdd1122334455667788"
            assert config["username"] == "user1"
            assert config["password"] == "pass1"
            assert config["verify_ssl"] is False
            assert config["site_id"] == "MySite"

    def test_no_shared_client_on_state(self) -> None:
        """No OmadaClient or OmadaAdapter should be stored on app.state."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="aabbccdd1122334455667788",
            omada_username="user1",
            omada_password="pass1",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert not hasattr(app.state, "omada_client")
            assert not hasattr(app.state, "omada_adapter")


class TestAdminLifespanOmadaNotConfigured:
    """Tests when Omada controller URL is not configured."""

    def test_omada_config_is_none(self) -> None:
        """app.state.omada_config should be None when URL is empty."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            assert app.state.omada_config is None

    def test_no_errors_when_unconfigured(self, caplog: pytest.LogCaptureFixture) -> None:
        """App should start without errors when Omada is not configured."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="",
        )
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
