# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for portal configuration validation."""

import pytest
from pydantic import ValidationError

from captive_portal.models.portal_config import PortalConfig


def test_portal_config_default_values() -> None:
    """Verify PortalConfig uses expected default values."""
    # WHEN: Creating config with no parameters
    config = PortalConfig()

    # THEN: Defaults are applied
    assert config.rate_limit_attempts == 5
    assert config.rate_limit_window_seconds == 60
    assert config.redirect_to_original_url is True


def test_portal_config_valid_custom_values() -> None:
    """Verify PortalConfig accepts valid custom values."""
    # WHEN: Creating config with valid custom values
    config = PortalConfig(
        rate_limit_attempts=10,
        rate_limit_window_seconds=120,
        redirect_to_original_url=False,
    )

    # THEN: Values are set correctly
    assert config.rate_limit_attempts == 10
    assert config.rate_limit_window_seconds == 120
    assert config.redirect_to_original_url is False


def test_portal_config_rate_limit_attempts_min_bound() -> None:
    """Verify rate_limit_attempts minimum bound validation."""
    # WHEN/THEN: Value below minimum raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        PortalConfig(rate_limit_attempts=0)

    errors = exc_info.value.errors()
    assert any(
        e["loc"] == ("rate_limit_attempts",) and "greater than or equal to 1" in str(e)
        for e in errors
    )


def test_portal_config_rate_limit_attempts_max_bound() -> None:
    """Verify rate_limit_attempts maximum bound validation."""
    # WHEN/THEN: Value above maximum raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        PortalConfig(rate_limit_attempts=1001)

    errors = exc_info.value.errors()
    assert any(
        e["loc"] == ("rate_limit_attempts",) and "less than or equal to 1000" in str(e)
        for e in errors
    )


def test_portal_config_rate_limit_window_min_bound() -> None:
    """Verify rate_limit_window_seconds minimum bound validation."""
    # WHEN/THEN: Value below minimum raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        PortalConfig(rate_limit_window_seconds=0)

    errors = exc_info.value.errors()
    assert any(
        e["loc"] == ("rate_limit_window_seconds",) and "greater than or equal to 1" in str(e)
        for e in errors
    )


def test_portal_config_rate_limit_window_max_bound() -> None:
    """Verify rate_limit_window_seconds maximum bound validation."""
    # WHEN/THEN: Value above maximum raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        PortalConfig(rate_limit_window_seconds=3601)

    errors = exc_info.value.errors()
    assert any(
        e["loc"] == ("rate_limit_window_seconds",) and "less than or equal to 3600" in str(e)
        for e in errors
    )


def test_portal_config_rate_limit_edge_cases() -> None:
    """Verify edge case values for rate limiting are valid."""
    # WHEN: Using edge case values
    config_min = PortalConfig(rate_limit_attempts=1, rate_limit_window_seconds=1)
    config_max = PortalConfig(rate_limit_attempts=1000, rate_limit_window_seconds=3600)

    # THEN: Values are accepted
    assert config_min.rate_limit_attempts == 1
    assert config_min.rate_limit_window_seconds == 1
    assert config_max.rate_limit_attempts == 1000
    assert config_max.rate_limit_window_seconds == 3600


def test_portal_config_redirect_boolean_type() -> None:
    """Verify redirect_to_original_url accepts boolean values."""
    # WHEN: Setting redirect flag
    config_true = PortalConfig(redirect_to_original_url=True)
    config_false = PortalConfig(redirect_to_original_url=False)

    # THEN: Boolean values are preserved
    assert config_true.redirect_to_original_url is True
    assert config_false.redirect_to_original_url is False


def test_portal_config_immutable_id() -> None:
    """Verify PortalConfig enforces singleton pattern via id=1."""
    # WHEN: Creating config instance
    config = PortalConfig()

    # THEN: ID is always 1 (singleton pattern)
    assert config.id == 1


def test_portal_config_invalid_types() -> None:
    """Verify PortalConfig rejects invalid data types."""
    # WHEN/THEN: Invalid types raise ValidationError
    with pytest.raises(ValidationError):
        PortalConfig(rate_limit_attempts="ten")

    with pytest.raises(ValidationError):
        PortalConfig(redirect_to_original_url="yes")
