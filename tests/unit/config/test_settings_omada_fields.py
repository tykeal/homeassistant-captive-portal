# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for 6 Omada settings fields in AppSettings.

Validates three-tier precedence (addon → env → default), boolean coercion,
password masking in log_effective(), and ``omada_configured`` property.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from captive_portal.config.settings import AppSettings


def _clean_env() -> dict[str, str]:
    """Return environment with all CP_ and SUPERVISOR_TOKEN vars removed."""
    return {
        k: v for k, v in os.environ.items() if not k.startswith("CP_") and k != "SUPERVISOR_TOKEN"
    }


class TestOmadaControllerUrl:
    """Tests for the omada_controller_url setting."""

    def test_default_empty_string(self) -> None:
        """omada_controller_url should default to empty string."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_controller_url == ""

    def test_env_var_overrides_default(self) -> None:
        """CP_OMADA_CONTROLLER_URL env var should override the default."""
        env = _clean_env()
        env["CP_OMADA_CONTROLLER_URL"] = "https://192.168.1.10:8043"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_controller_url == "https://192.168.1.10:8043"

    def test_addon_option_overrides_env(self, tmp_path: Path) -> None:
        """Addon option should take precedence over env var."""
        opts = {"omada_controller_url": "https://addon.local:8043"}
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(opts))

        env = _clean_env()
        env["CP_OMADA_CONTROLLER_URL"] = "https://env.local:8043"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path=str(opts_file))
        assert settings.omada_controller_url == "https://addon.local:8043"


class TestOmadaUsername:
    """Tests for the omada_username setting."""

    def test_default_empty_string(self) -> None:
        """omada_username should default to empty string."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_username == ""

    def test_env_var_overrides_default(self) -> None:
        """CP_OMADA_USERNAME env var should override the default."""
        env = _clean_env()
        env["CP_OMADA_USERNAME"] = "hotspot_operator"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_username == "hotspot_operator"

    def test_addon_option_overrides_env(self, tmp_path: Path) -> None:
        """Addon option should take precedence over env var."""
        opts = {"omada_username": "addon_user"}
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(opts))

        env = _clean_env()
        env["CP_OMADA_USERNAME"] = "env_user"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path=str(opts_file))
        assert settings.omada_username == "addon_user"


class TestOmadaPassword:
    """Tests for the omada_password setting."""

    def test_default_empty_string(self) -> None:
        """omada_password should default to empty string."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_password == ""

    def test_env_var_overrides_default(self) -> None:
        """CP_OMADA_PASSWORD env var should override the default."""
        env = _clean_env()
        env["CP_OMADA_PASSWORD"] = "s3cret"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_password == "s3cret"

    def test_addon_option_overrides_env(self, tmp_path: Path) -> None:
        """Addon option should take precedence over env var."""
        opts = {"omada_password": "addon_pass"}
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(opts))

        env = _clean_env()
        env["CP_OMADA_PASSWORD"] = "env_pass"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path=str(opts_file))
        assert settings.omada_password == "addon_pass"


class TestOmadaSiteName:
    """Tests for the omada_site_name setting."""

    def test_default_is_default(self) -> None:
        """omada_site_name should default to 'Default'."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_site_name == "Default"

    def test_env_var_overrides_default(self) -> None:
        """CP_OMADA_SITE_NAME env var should override the default."""
        env = _clean_env()
        env["CP_OMADA_SITE_NAME"] = "MySite"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_site_name == "MySite"

    def test_addon_option_overrides_env(self, tmp_path: Path) -> None:
        """Addon option should take precedence over env var."""
        opts = {"omada_site_name": "AddonSite"}
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(opts))

        env = _clean_env()
        env["CP_OMADA_SITE_NAME"] = "EnvSite"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path=str(opts_file))
        assert settings.omada_site_name == "AddonSite"


class TestOmadaControllerId:
    """Tests for the omada_controller_id setting."""

    def test_default_empty_string(self) -> None:
        """omada_controller_id should default to empty string."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_controller_id == ""

    def test_env_var_overrides_default(self) -> None:
        """CP_OMADA_CONTROLLER_ID env var should override the default."""
        env = _clean_env()
        env["CP_OMADA_CONTROLLER_ID"] = "ctrl-abc123"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_controller_id == "ctrl-abc123"


class TestOmadaVerifySsl:
    """Tests for the omada_verify_ssl setting."""

    def test_default_true(self) -> None:
        """omada_verify_ssl should default to True."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_verify_ssl is True

    def test_env_var_false_string(self) -> None:
        """CP_OMADA_VERIFY_SSL='false' should coerce to False."""
        env = _clean_env()
        env["CP_OMADA_VERIFY_SSL"] = "false"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_verify_ssl is False

    def test_env_var_true_string(self) -> None:
        """CP_OMADA_VERIFY_SSL='true' should coerce to True."""
        env = _clean_env()
        env["CP_OMADA_VERIFY_SSL"] = "true"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_verify_ssl is True

    def test_env_var_zero(self) -> None:
        """CP_OMADA_VERIFY_SSL='0' should coerce to False."""
        env = _clean_env()
        env["CP_OMADA_VERIFY_SSL"] = "0"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_verify_ssl is False

    def test_env_var_one(self) -> None:
        """CP_OMADA_VERIFY_SSL='1' should coerce to True."""
        env = _clean_env()
        env["CP_OMADA_VERIFY_SSL"] = "1"
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path="/nonexistent/options.json")
        assert settings.omada_verify_ssl is True

    def test_addon_bool_false(self, tmp_path: Path) -> None:
        """Addon option boolean false should set omada_verify_ssl to False."""
        opts = {"omada_verify_ssl": False}
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(opts))

        with patch.dict(os.environ, _clean_env(), clear=True):
            settings = AppSettings.load(options_path=str(opts_file))
        assert settings.omada_verify_ssl is False


class TestOmadaLogEffective:
    """Tests for password masking in log_effective()."""

    def test_password_logged_as_set_when_present(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_effective should show '(set)' when password is configured."""
        settings = AppSettings(omada_password="s3cret-p@ss!")
        with caplog.at_level(logging.INFO):
            settings.log_effective(logging.getLogger("test"))

        log_text = caplog.text
        assert "(set)" in log_text
        assert "s3cret-p@ss!" not in log_text

    def test_password_logged_as_not_set_when_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_effective should show '(not set)' when password is empty."""
        settings = AppSettings(omada_password="")
        with caplog.at_level(logging.INFO):
            settings.log_effective(logging.getLogger("test"))

        log_text = caplog.text
        assert "(not set)" in log_text

    def test_all_omada_fields_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_effective should log all 6 Omada fields."""
        settings = AppSettings(
            omada_controller_url="https://ctrl.local:8043",
            omada_username="user1",
            omada_password="pass1",
            omada_site_name="TestSite",
            omada_controller_id="ctrl-123",
            omada_verify_ssl=False,
        )
        with caplog.at_level(logging.INFO):
            settings.log_effective(logging.getLogger("test"))

        log_text = caplog.text
        assert "omada_controller_url" in log_text
        assert "https://ctrl.local:8043" in log_text
        assert "omada_username" in log_text
        assert "omada_site_name" in log_text
        assert "omada_controller_id" in log_text
        assert "omada_verify_ssl" in log_text


class TestOmadaConfigured:
    """Tests for the omada_configured property."""

    def test_configured_when_url_and_id_present(self) -> None:
        """omada_configured should be True when URL and ID are non-empty."""
        settings = AppSettings(
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="abc123",
        )
        assert settings.omada_configured is True

    def test_not_configured_when_url_empty(self) -> None:
        """omada_configured should be False when URL is empty."""
        settings = AppSettings(
            omada_controller_url="",
            omada_controller_id="abc123",
        )
        assert settings.omada_configured is False

    def test_not_configured_when_id_empty(self) -> None:
        """omada_configured should be False when controller_id is empty."""
        settings = AppSettings(
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="",
        )
        assert settings.omada_configured is False

    def test_not_configured_when_id_whitespace(self) -> None:
        """omada_configured should be False when controller_id is whitespace."""
        settings = AppSettings(
            omada_controller_url="https://ctrl.local:8043",
            omada_controller_id="   ",
        )
        assert settings.omada_configured is False

    def test_not_configured_when_url_whitespace(self) -> None:
        """omada_configured should be False when URL is whitespace."""
        settings = AppSettings(
            omada_controller_url="   ",
            omada_controller_id="abc123",
        )
        assert settings.omada_configured is False

    def test_not_configured_by_default(self) -> None:
        """omada_configured should be False with defaults."""
        settings = AppSettings()
        assert settings.omada_configured is False
