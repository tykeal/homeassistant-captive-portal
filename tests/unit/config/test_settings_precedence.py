# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test three-tier settings precedence: addon option > env var > default."""

import json
import os
import tempfile
from unittest.mock import patch

from captive_portal.config.settings import AppSettings


def test_addon_option_overrides_env_var() -> None:
    """Addon option takes precedence over env var for same field."""
    options = {"log_level": "warning"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        with patch.dict(os.environ, {"CP_LOG_LEVEL": "debug"}, clear=False):
            settings = AppSettings.load(options_path=path)

        # Addon option "warning" wins over env var "debug"
        assert settings.log_level == "warning"
    finally:
        os.unlink(path)


def test_env_var_overrides_default() -> None:
    """Env var takes precedence over built-in default."""
    env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
    env_clear["CP_DB_PATH"] = "/custom/db.sqlite"
    with patch.dict(os.environ, env_clear, clear=True):
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    assert settings.db_path == "/custom/db.sqlite"


def test_invalid_addon_falls_through_to_env() -> None:
    """Invalid addon option falls through to valid env var."""
    options = {"log_level": "banana"}  # invalid
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        with patch.dict(os.environ, {"CP_LOG_LEVEL": "error"}, clear=False):
            settings = AppSettings.load(options_path=path)

        # Addon "banana" invalid → env "error" used
        assert settings.log_level == "error"
    finally:
        os.unlink(path)


def test_invalid_addon_no_env_falls_to_default() -> None:
    """Invalid addon option + no env var → built-in default."""
    options = {"log_level": "banana"}  # invalid
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        # No env var, addon invalid → default "info"
        assert settings.log_level == "info"
    finally:
        os.unlink(path)


def test_valid_addon_kept_while_invalid_one_falls_through() -> None:
    """Valid addon options are kept even when one is invalid."""
    options = {
        "log_level": "debug",  # valid
        "ha_base_url": "not-a-url",  # invalid
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        env_clear["CP_HA_BASE_URL"] = "https://env-ha.local/api"
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "debug"  # from addon (valid)
        assert settings.ha_base_url == "https://env-ha.local/api"  # addon invalid → env
    finally:
        os.unlink(path)


def test_all_fields_independently() -> None:
    """Each field's precedence is independent of other fields."""
    options = {
        "log_level": "trace",  # from addon
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        env["CP_DB_PATH"] = "/custom/db.sqlite"  # from env
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "trace"  # addon
        assert settings.db_path == "/custom/db.sqlite"  # env
    finally:
        os.unlink(path)


def test_invalid_env_var_falls_to_default() -> None:
    """Invalid env var with no addon option falls to default."""
    env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
    env_clear["CP_LOG_LEVEL"] = "not_valid_level"
    with patch.dict(os.environ, env_clear, clear=True):
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    assert settings.log_level == "info"  # default
