# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for addon config application.

Validates that AppSettings.load() reads addon options.json and applies
settings to the application correctly.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from unittest.mock import patch

from captive_portal.config.settings import AppSettings


def test_load_with_options_json_all_fields() -> None:
    """AppSettings.load() with full options.json produces correct settings."""
    options = {
        "log_level": "debug",
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
    finally:
        os.unlink(path)


def test_empty_options_produces_defaults() -> None:
    """Empty options {} results in all defaults."""
    options: dict[str, object] = {}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(options, f)
        f.flush()
        path = f.name

    try:
        env_clear = {k: v for k, v in os.environ.items() if not k.startswith("CP_")}
        with patch.dict(os.environ, env_clear, clear=True):
            settings = AppSettings.load(options_path=path)

        assert settings.log_level == "info"
    finally:
        os.unlink(path)


def test_debug_level_produces_debug_log_config() -> None:
    """Debug-level settings produce DEBUG in log config."""
    settings = AppSettings(log_level="debug")
    log_cfg = settings.to_log_config()
    assert log_cfg["level"] == logging.DEBUG
