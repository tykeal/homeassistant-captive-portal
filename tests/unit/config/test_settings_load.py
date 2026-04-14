# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test configuration settings loading."""

import logging
import os
from unittest.mock import patch

import pytest

from captive_portal.config.settings import AppSettings


def test_settings_load_defaults() -> None:
    """Settings should load with sensible defaults when env vars absent."""
    # GIVEN: no environment variables set and no addon options file
    env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
    with patch.dict(os.environ, env_clear, clear=True):
        # WHEN: loading settings with non-existent options file
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    # THEN: defaults applied
    assert settings.log_level == "info"
    assert settings.db_path == "/data/captive_portal.db"


def test_settings_load_from_env() -> None:
    """Settings should load from environment variables."""
    # GIVEN: env vars with CP_ prefix
    env_overrides = {
        "CP_LOG_LEVEL": "debug",
        "CP_DB_PATH": "/custom/path.db",
    }
    with patch.dict(os.environ, env_overrides, clear=False):
        # WHEN: loading settings with no addon options file
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    # THEN: settings reflect env values
    assert settings.log_level == "debug"
    assert settings.db_path == "/custom/path.db"


def test_invalid_log_level_falls_back_to_default() -> None:
    """Settings should ignore invalid env var values and use defaults."""
    # GIVEN: env var with invalid log level
    with patch.dict(os.environ, {"CP_LOG_LEVEL": "banana"}, clear=False):
        # WHEN: loading settings
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    # THEN: falls through to default
    assert settings.log_level == "info"


def test_settings_secret_redaction() -> None:
    """No secrets should appear in string representation."""
    # GIVEN: settings with defaults
    settings = AppSettings.load(options_path="/nonexistent/options.json")

    # WHEN: converting to string
    repr_str = repr(settings)

    # THEN: only known safe fields appear, no sensitive tokens
    assert "db_path" in repr_str
    assert "log_level" in repr_str
    # AppSettings currently has no secret fields, but verify db_path is
    # shown (not redacted) since it's not a secret
    assert "/data/captive_portal.db" in repr_str


def test_settings_database_path_default() -> None:
    """Default DB path should be /data/captive_portal.db."""
    # GIVEN: no env vars or addon options
    env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
    with patch.dict(os.environ, env_clear, clear=True):
        # WHEN: loading settings
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    # THEN: defaults to addon path
    assert settings.db_path == "/data/captive_portal.db"


def test_settings_log_effective(caplog: pytest.LogCaptureFixture) -> None:
    """log_effective() should log retained settings at INFO level."""
    # GIVEN: settings with defaults
    settings = AppSettings.load(options_path="/nonexistent/options.json")
    logger = logging.getLogger("test_settings_load")

    # WHEN: logging effective settings
    with caplog.at_level(logging.INFO, logger="test_settings_load"):
        settings.log_effective(logger)

    # THEN: retained fields logged
    assert "log_level" in caplog.text
    assert "db_path" in caplog.text
    assert "ha_base_url" in caplog.text
    assert "debug_guest_portal" in caplog.text
