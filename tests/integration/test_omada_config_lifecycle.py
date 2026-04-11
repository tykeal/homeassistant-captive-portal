# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration test for end-to-end Omada config lifecycle.

Validates that CP_OMADA_* env vars flow through AppSettings into
app.state.omada_config and that get_omada_adapter creates correct
adapter instances.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from captive_portal.config.settings import AppSettings
from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import OmadaClient
from captive_portal.controllers.tp_omada.dependencies import get_omada_adapter


def _clean_env() -> dict[str, str]:
    """Return environment with all CP_ and SUPERVISOR_TOKEN vars removed."""
    return {
        k: v for k, v in os.environ.items() if not k.startswith("CP_") and k != "SUPERVISOR_TOKEN"
    }


class TestOmadaConfigLifecycle:
    """End-to-end tests for the Omada configuration lifecycle."""

    def test_env_vars_flow_into_app_state(self) -> None:
        """CP_OMADA_* env vars should populate app.state.omada_config."""
        env = _clean_env()
        env.update(
            {
                "CP_OMADA_CONTROLLER_URL": "https://192.168.1.10:8043",
                "CP_OMADA_CONTROLLER_ID": "ctrl-test-123",
                "CP_OMADA_USERNAME": "hotspot_user",
                "CP_OMADA_PASSWORD": "test_pass",
                "CP_OMADA_VERIFY_SSL": "false",
                "CP_OMADA_SITE_NAME": "TestSite",
            }
        )
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")

        # Override db_path for test (no /data directory in test env)
        settings = settings.model_copy(update={"db_path": ":memory:"})

        from captive_portal.app import create_app

        app = create_app(settings=settings)
        with TestClient(app):
            config = app.state.omada_config
            assert config is not None
            assert config["base_url"] == "https://192.168.1.10:8043"
            assert config["controller_id"] == "ctrl-test-123"
            assert config["username"] == "hotspot_user"
            assert config["password"] == "test_pass"
            assert config["verify_ssl"] is False
            assert config["site_id"] == "TestSite"

    def test_env_vars_flow_into_guest_app_state(self) -> None:
        """CP_OMADA_* env vars should populate guest app.state.omada_config."""
        env = _clean_env()
        env.update(
            {
                "CP_OMADA_CONTROLLER_URL": "https://192.168.1.10:8043",
                "CP_OMADA_CONTROLLER_ID": "ctrl-test-123",
                "CP_OMADA_USERNAME": "hotspot_user",
                "CP_OMADA_PASSWORD": "test_pass",
                "CP_OMADA_VERIFY_SSL": "true",
                "CP_OMADA_SITE_NAME": "GuestSite",
            }
        )
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")

        # Override db_path for test (no /data directory in test env)
        settings = settings.model_copy(update={"db_path": ":memory:"})

        from captive_portal.guest_app import create_guest_app

        app = create_guest_app(settings=settings)
        with TestClient(app):
            config = app.state.omada_config
            assert config is not None
            assert config["base_url"] == "https://192.168.1.10:8043"
            assert config["verify_ssl"] is True
            assert config["site_id"] == "GuestSite"

    def test_adapter_created_from_config(self) -> None:
        """get_omada_adapter should create adapter from app.state.omada_config."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="ctrl-abc",
            omada_username="user1",
            omada_password="pass1",
            omada_verify_ssl=False,
            omada_site_name="TestSite",
        )
        from captive_portal.app import create_app
        from unittest.mock import MagicMock

        app = create_app(settings=settings)
        with TestClient(app):
            # Simulate a request to get adapter
            mock_request = MagicMock()
            mock_request.app = app
            adapter = get_omada_adapter(mock_request)

            assert adapter is not None
            assert isinstance(adapter, OmadaAdapter)
            assert isinstance(adapter.client, OmadaClient)
            assert adapter.client.base_url == "https://ctrl.local:8043"
            assert adapter.site_id == "TestSite"

    def test_no_startup_network_io(self) -> None:
        """No network I/O should occur during app startup."""
        settings = AppSettings(
            db_path=":memory:",
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="ctrl-abc",
            omada_username="user1",
            omada_password="pass1",
        )
        from captive_portal.app import create_app

        app = create_app(settings=settings)
        # If startup tried to connect, it would fail (no controller)
        # The fact that TestClient starts without error proves no I/O
        with TestClient(app) as client:
            resp = client.get("/api/live")
            assert resp.status_code == 200
