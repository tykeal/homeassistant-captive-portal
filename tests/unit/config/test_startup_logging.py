# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test startup logging of effective configuration."""

from __future__ import annotations

import logging

import pytest

from captive_portal.config.settings import AppSettings


def test_log_effective_logs_all_settings(caplog: pytest.LogCaptureFixture) -> None:
    """log_effective() should log all retained settings at INFO level."""
    settings = AppSettings(
        log_level="debug",
        db_path="/data/test.db",
    )
    logger = logging.getLogger("test_startup_logging")

    with caplog.at_level(logging.INFO, logger="test_startup_logging"):
        settings.log_effective(logger)

    assert "log_level" in caplog.text
    assert "debug" in caplog.text
    assert "db_path" in caplog.text
    assert "/data/test.db" in caplog.text
    assert "ha_base_url" in caplog.text
    assert "debug_guest_portal" in caplog.text


def test_log_effective_no_secrets(caplog: pytest.LogCaptureFixture) -> None:
    """log_effective() should not contain sensitive values."""
    settings = AppSettings()
    logger = logging.getLogger("test_startup_nosecrets")

    with caplog.at_level(logging.INFO, logger="test_startup_nosecrets"):
        settings.log_effective(logger)

    # Actual setting values should not contain password, token, or key
    log_lines = caplog.text.lower()
    for secret_word in ("password=", "token=", "api_key="):
        assert secret_word not in log_lines


def test_log_effective_includes_field_names_and_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log output should include both field names and effective values."""
    settings = AppSettings(
        log_level="warning",
        db_path="/custom/db.sqlite",
    )
    logger = logging.getLogger("test_startup_fields")

    with caplog.at_level(logging.INFO, logger="test_startup_fields"):
        settings.log_effective(logger)

    # Field names present
    for field in ("log_level", "db_path", "ha_base_url", "debug_guest_portal"):
        assert field in caplog.text

    # Values present
    assert "warning" in caplog.text
    assert "/custom/db.sqlite" in caplog.text
