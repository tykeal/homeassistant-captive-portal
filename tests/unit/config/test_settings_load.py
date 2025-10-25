# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test configuration settings loading."""

import pytest


def test_settings_load_defaults() -> None:
    """Settings should load with sensible defaults when env vars absent."""
    # GIVEN: no environment variables set
    # WHEN: loading settings
    # THEN: defaults applied (e.g., LOG_LEVEL=INFO, DB_PATH=/data/captive_portal.db)
    pytest.skip("Config module not implemented yet")


def test_settings_load_from_env() -> None:
    """Settings should load from environment variables."""
    # GIVEN: env vars CP_LOG_LEVEL=DEBUG, CP_DB_PATH=/custom/path.db
    # WHEN: loading settings
    # THEN: settings reflect env values
    pytest.skip("Config module not implemented yet")


def test_settings_validation_error_on_invalid() -> None:
    """Settings should raise validation error on invalid values."""
    # GIVEN: env var with invalid type (e.g., CP_VOUCHER_MIN_LENGTH=-1)
    # WHEN: loading settings
    # THEN: ValidationError raised
    pytest.skip("Config module not implemented yet")


def test_settings_secret_redaction() -> None:
    """Secrets (passwords, API keys) should be redacted in logs/repr."""
    # GIVEN: settings with HA_API_TOKEN=secret123
    # WHEN: converting to string
    # THEN: token redacted (shows *****)
    pytest.skip("Config module not implemented yet")


def test_settings_database_path_default() -> None:
    """Default DB path should differ for addon vs standalone."""
    # GIVEN: settings with addon mode enabled
    # WHEN: loading DB_PATH
    # THEN: defaults to /data/captive_portal.db
    # GIVEN: settings with addon mode disabled
    # THEN: defaults to /var/lib/captive-portal/captive_portal.db
    pytest.skip("Config module not implemented yet")
