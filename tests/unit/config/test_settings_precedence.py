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
    env_clear["CP_SESSION_IDLE_TIMEOUT"] = "45"
    with patch.dict(os.environ, env_clear, clear=True):
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    assert settings.session_idle_minutes == 45


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
    options = {"session_idle_timeout": -5}  # invalid
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        # No env var, addon invalid → default 30
        assert settings.session_idle_minutes == 30
    finally:
        os.unlink(path)


def test_valid_addon_kept_while_invalid_one_falls_through() -> None:
    """Valid addon options are kept even when one is invalid."""
    options = {
        "log_level": "debug",  # valid
        "session_idle_timeout": -5,  # invalid
        "session_max_duration": 12,  # valid
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        env_clear["CP_SESSION_IDLE_TIMEOUT"] = "20"
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "debug"  # from addon (valid)
        assert settings.session_idle_minutes == 20  # addon invalid → env
        assert settings.session_max_hours == 12  # from addon (valid)
    finally:
        os.unlink(path)


def test_all_four_fields_independently() -> None:
    """Each field's precedence is independent of other fields."""
    options = {
        "log_level": "trace",  # from addon
        # session_idle_timeout missing → env or default
        "session_max_duration": 2,  # from addon
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        env["CP_DB_PATH"] = "/custom/db.sqlite"  # from env
        env["CP_SESSION_IDLE_TIMEOUT"] = "60"  # from env
        with patch.dict(os.environ, env, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "trace"  # addon
        assert settings.db_path == "/custom/db.sqlite"  # env
        assert settings.session_idle_minutes == 60  # env (no addon)
        assert settings.session_max_hours == 2  # addon
    finally:
        os.unlink(path)


def test_invalid_env_var_falls_to_default() -> None:
    """Invalid env var with no addon option falls to default."""
    env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
    env_clear["CP_SESSION_MAX_DURATION"] = "not_a_number"
    with patch.dict(os.environ, env_clear, clear=True):
        settings = AppSettings.load(options_path="/nonexistent/options.json")

    assert settings.session_max_hours == 8  # default
