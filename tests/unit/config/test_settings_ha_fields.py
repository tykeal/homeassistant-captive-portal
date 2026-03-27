# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for HA-specific AppSettings fields (ha_base_url, ha_token)."""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

import pytest

from captive_portal.config.settings import AppSettings


# ---------------------------------------------------------------------------
# ha_base_url defaults
# ---------------------------------------------------------------------------


class TestHaBaseUrl:
    """Tests for the ha_base_url setting."""

    def test_default_ha_base_url(self) -> None:
        """ha_base_url should default to the Supervisor core API endpoint."""
        env_clear = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("CP_") and k != "SUPERVISOR_TOKEN"
        }
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_base_url == "http://supervisor/core/api"

    def test_env_var_overrides_ha_base_url(self) -> None:
        """CP_HA_BASE_URL env var should override the default."""
        with patch.dict(
            os.environ,
            {"CP_HA_BASE_URL": "https://my-ha.local:8123/api"},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_base_url == "https://my-ha.local:8123/api"

    def test_addon_option_overrides_env_var(self, tmp_path: object) -> None:
        """Addon option ha_base_url should take precedence over env var."""
        from pathlib import Path

        opts = {"ha_base_url": "https://addon-option.local/api"}
        opts_file = Path(str(tmp_path)) / "options.json"
        opts_file.write_text(json.dumps(opts))

        with patch.dict(
            os.environ,
            {"CP_HA_BASE_URL": "https://env-var.local/api"},
            clear=False,
        ):
            settings = AppSettings.load(options_path=str(opts_file))
        assert settings.ha_base_url == "https://addon-option.local/api"

    def test_invalid_ha_base_url_falls_back(self) -> None:
        """Invalid ha_base_url env var should fall through to default."""
        with patch.dict(
            os.environ,
            {"CP_HA_BASE_URL": "not-a-url"},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_base_url == "http://supervisor/core/api"

    def test_ha_base_url_strips_whitespace(self) -> None:
        """Whitespace should be stripped from ha_base_url."""
        with patch.dict(
            os.environ,
            {"CP_HA_BASE_URL": "  https://trimmed.local/api  "},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_base_url == "https://trimmed.local/api"


# ---------------------------------------------------------------------------
# ha_token
# ---------------------------------------------------------------------------


class TestHaToken:
    """Tests for the ha_token setting."""

    def test_supervisor_token_is_primary(self) -> None:
        """SUPERVISOR_TOKEN env var should be the primary source for ha_token."""
        with patch.dict(
            os.environ,
            {"SUPERVISOR_TOKEN": "sv-tok-123"},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_token == "sv-tok-123"

    def test_cp_ha_token_is_fallback(self) -> None:
        """CP_HA_TOKEN env var should be the fallback when SUPERVISOR_TOKEN missing."""
        env_clear = {k: v for k, v in os.environ.items() if k != "SUPERVISOR_TOKEN"}
        with patch.dict(os.environ, {**env_clear, "CP_HA_TOKEN": "cp-tok-456"}, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_token == "cp-tok-456"

    def test_supervisor_token_takes_precedence_over_cp(self) -> None:
        """SUPERVISOR_TOKEN should take precedence over CP_HA_TOKEN."""
        with patch.dict(
            os.environ,
            {"SUPERVISOR_TOKEN": "sv-tok-win", "CP_HA_TOKEN": "cp-tok-lose"},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_token == "sv-tok-win"

    def test_missing_token_defaults_to_empty(self) -> None:
        """Missing SUPERVISOR_TOKEN and CP_HA_TOKEN should default to empty string."""
        env_clear = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("CP_") and k != "SUPERVISOR_TOKEN"
        }
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_token == ""

    def test_ha_token_strips_whitespace(self) -> None:
        """Whitespace should be stripped from ha_token."""
        with patch.dict(
            os.environ,
            {"SUPERVISOR_TOKEN": "  tok-spaces  "},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.ha_token == "tok-spaces"


# ---------------------------------------------------------------------------
# log_effective masking
# ---------------------------------------------------------------------------


class TestLogEffective:
    """Tests for log_effective masking of ha_token."""

    def test_log_effective_masks_ha_token_when_set(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_effective should show '(set)' for ha_token when a token exists."""
        with patch.dict(
            os.environ,
            {"SUPERVISOR_TOKEN": "secret-value"},
            clear=False,
        ):
            settings = AppSettings.load(options_path="/nonexistent/options.json")

        log = logging.getLogger("test_ha_fields")
        with caplog.at_level(logging.INFO, logger="test_ha_fields"):
            settings.log_effective(log)

        assert "ha_token" in caplog.text
        assert "(set)" in caplog.text
        assert "secret-value" not in caplog.text

    def test_log_effective_shows_not_set_when_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_effective should show '(not set)' for ha_token when empty."""
        env_clear = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("CP_") and k != "SUPERVISOR_TOKEN"
        }
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")

        log = logging.getLogger("test_ha_fields")
        with caplog.at_level(logging.INFO, logger="test_ha_fields"):
            settings.log_effective(log)

        assert "(not set)" in caplog.text

    def test_log_effective_shows_ha_base_url(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_effective should show ha_base_url."""
        settings = AppSettings.load(options_path="/nonexistent/options.json")
        log = logging.getLogger("test_ha_fields")
        with caplog.at_level(logging.INFO, logger="test_ha_fields"):
            settings.log_effective(log)
        assert "ha_base_url" in caplog.text
