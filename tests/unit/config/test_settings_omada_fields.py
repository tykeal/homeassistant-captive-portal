# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for _load_for_migration() legacy field loading.

Validates that migrated settings (Omada, session, guest URL) are
still readable from YAML / env vars via the migration helper, even
though they no longer exist on AppSettings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from captive_portal.config.settings import AppSettings


def _clean_env() -> dict[str, str]:
    """Return environment with all CP_ and SUPERVISOR_TOKEN vars removed."""
    return {
        k: v for k, v in os.environ.items() if not k.startswith("CP_") and k != "SUPERVISOR_TOKEN"
    }


class TestMigrationDefaults:
    """Tests for default values from _load_for_migration."""

    def test_defaults_returned(self) -> None:
        """_load_for_migration returns sensible defaults."""
        with patch.dict(os.environ, _clean_env(), clear=True):
            legacy = AppSettings._load_for_migration(options_path="/nonexistent/options.json")
        assert legacy["session_idle_minutes"] == 30
        assert legacy["session_max_hours"] == 8
        assert legacy["guest_external_url"] == ""
        assert legacy["omada_controller_url"] == ""
        assert legacy["omada_username"] == ""
        assert legacy["omada_password"] == ""
        assert legacy["omada_site_name"] == "Default"
        assert legacy["omada_controller_id"] == ""
        assert legacy["omada_verify_ssl"] is True


class TestMigrationFromEnvVars:
    """Tests for _load_for_migration reading env vars."""

    def test_omada_env_vars_read(self) -> None:
        """CP_OMADA_* env vars should be read by migration helper."""
        env = _clean_env()
        env["CP_OMADA_CONTROLLER_URL"] = "https://192.168.1.10:8043"
        env["CP_OMADA_USERNAME"] = "hotspot_operator"
        env["CP_OMADA_PASSWORD"] = "s3cret"
        env["CP_OMADA_SITE_NAME"] = "MySite"
        env["CP_OMADA_VERIFY_SSL"] = "false"
        with patch.dict(os.environ, env, clear=True):
            legacy = AppSettings._load_for_migration(options_path="/nonexistent/options.json")
        assert legacy["omada_controller_url"] == "https://192.168.1.10:8043"
        assert legacy["omada_username"] == "hotspot_operator"
        assert legacy["omada_password"] == "s3cret"
        assert legacy["omada_site_name"] == "MySite"
        assert legacy["omada_verify_ssl"] is False

    def test_session_env_vars_read(self) -> None:
        """CP_SESSION_* env vars should be read by migration helper."""
        env = _clean_env()
        env["CP_SESSION_IDLE_TIMEOUT"] = "45"
        env["CP_SESSION_MAX_DURATION"] = "12"
        with patch.dict(os.environ, env, clear=True):
            legacy = AppSettings._load_for_migration(options_path="/nonexistent/options.json")
        assert legacy["session_idle_minutes"] == 45
        assert legacy["session_max_hours"] == 12

    def test_guest_url_env_var_read(self) -> None:
        """CP_GUEST_EXTERNAL_URL env var should be read."""
        env = _clean_env()
        env["CP_GUEST_EXTERNAL_URL"] = "http://10.0.0.1:8099"
        with patch.dict(os.environ, env, clear=True):
            legacy = AppSettings._load_for_migration(options_path="/nonexistent/options.json")
        assert legacy["guest_external_url"] == "http://10.0.0.1:8099"


class TestMigrationFromAddonOptions:
    """Tests for _load_for_migration reading addon options."""

    def test_addon_option_overrides_env(self, tmp_path: Path) -> None:
        """Addon option takes precedence over env var."""
        opts = {"omada_controller_url": "https://addon.local:8043"}
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(opts))

        env = _clean_env()
        env["CP_OMADA_CONTROLLER_URL"] = "https://env.local:8043"
        with patch.dict(os.environ, env, clear=True):
            legacy = AppSettings._load_for_migration(options_path=str(opts_file))
        assert legacy["omada_controller_url"] == "https://addon.local:8043"


class TestMigrationFieldsNotOnSettings:
    """Verify migrated fields are NOT on AppSettings."""

    def test_no_omada_fields(self) -> None:
        """AppSettings should not have omada_* attributes."""
        settings = AppSettings()
        assert not hasattr(settings, "omada_controller_url")
        assert not hasattr(settings, "omada_username")
        assert not hasattr(settings, "omada_password")
        assert not hasattr(settings, "omada_configured")

    def test_no_session_fields(self) -> None:
        """AppSettings should not have session_idle_minutes."""
        settings = AppSettings()
        assert not hasattr(settings, "session_idle_minutes")
        assert not hasattr(settings, "session_max_hours")

    def test_no_guest_url_field(self) -> None:
        """AppSettings should not have guest_external_url."""
        settings = AppSettings()
        assert not hasattr(settings, "guest_external_url")
