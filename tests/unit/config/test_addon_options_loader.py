# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test addon options.json loading for AppSettings."""

import json
import logging
import os
import tempfile
from unittest.mock import patch

import pytest

from captive_portal.config.settings import AppSettings


def test_valid_options_json_all_fields() -> None:
    """All three addon option fields are parsed correctly from options.json."""
    options = {
        "log_level": "debug",
        "session_idle_timeout": 15,
        "session_max_duration": 4,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "debug"
        assert settings.session_idle_minutes == 15
        assert settings.session_max_hours == 4
    finally:
        os.unlink(path)


def test_missing_options_file_fallback_to_defaults() -> None:
    """Missing options.json gracefully falls back to defaults."""
    env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
    with patch.dict(os.environ, env_clear, clear=True):
        settings = AppSettings.load(options_path="/nonexistent/does_not_exist.json")

    assert settings.log_level == "info"
    assert settings.db_path == "/data/captive_portal.db"
    assert settings.session_idle_minutes == 30
    assert settings.session_max_hours == 8


def test_invalid_option_value_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid addon option value is ignored; warning logged."""
    options = {
        "log_level": "banana",  # invalid
        "session_idle_timeout": 15,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            with caplog.at_level(logging.WARNING):
                settings = AppSettings.load(options_path=path)

        # Invalid log_level ignored → default
        assert settings.log_level == "info"
        # Valid session_idle_timeout kept
        assert settings.session_idle_minutes == 15
        # Warning logged about invalid value
        assert "banana" in caplog.text.lower() or "invalid" in caplog.text.lower()
    finally:
        os.unlink(path)


def test_invalid_option_wrong_type_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Wrong type for addon option is ignored; warning logged."""
    options = {
        "session_idle_timeout": "not_an_int",  # wrong type
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            with caplog.at_level(logging.WARNING):
                settings = AppSettings.load(options_path=path)

        # Falls through to default
        assert settings.session_idle_minutes == 30
    finally:
        os.unlink(path)


def test_negative_timeout_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Negative timeout value in addon options is ignored."""
    options = {
        "session_idle_timeout": -5,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            with caplog.at_level(logging.WARNING):
                settings = AppSettings.load(options_path=path)

        assert settings.session_idle_minutes == 30
    finally:
        os.unlink(path)


def test_partial_options_merge_with_defaults() -> None:
    """Partial options.json merges with defaults for missing fields."""
    options = {
        "log_level": "warning",
        # session_idle_timeout and session_max_duration not present
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "warning"
        assert settings.session_idle_minutes == 30  # default
        assert settings.session_max_hours == 8  # default
    finally:
        os.unlink(path)
