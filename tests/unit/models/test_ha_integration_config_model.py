# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test HAIntegrationConfig model validation."""

from uuid import uuid4

import pytest

from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr


def test_ha_integration_config_defaults() -> None:
    """Test HAIntegrationConfig default values."""
    config = HAIntegrationConfig(
        id=uuid4(),
        integration_id="test_rental_control",
    )

    assert config.identifier_attr == IdentifierAttr.SLOT_CODE
    assert config.checkout_grace_minutes == 15
    assert config.last_sync_utc is None
    assert config.stale_count == 0


def test_ha_integration_config_custom_values() -> None:
    """Test HAIntegrationConfig with custom values."""
    config_id = uuid4()
    config = HAIntegrationConfig(
        id=config_id,
        integration_id="custom_integration",
        identifier_attr=IdentifierAttr.SLOT_NAME,
        checkout_grace_minutes=20,
    )

    assert config.id == config_id
    assert config.integration_id == "custom_integration"
    assert config.identifier_attr == IdentifierAttr.SLOT_NAME
    assert config.checkout_grace_minutes == 20


def test_grace_period_minimum_0() -> None:
    """Test that grace period accepts 0 (disabled)."""
    config = HAIntegrationConfig(
        id=uuid4(),
        integration_id="test",
        checkout_grace_minutes=0,
    )

    assert config.checkout_grace_minutes == 0


def test_grace_period_maximum_30() -> None:
    """Test that grace period accepts 30 (maximum)."""
    config = HAIntegrationConfig(
        id=uuid4(),
        integration_id="test",
        checkout_grace_minutes=30,
    )

    assert config.checkout_grace_minutes == 30


def test_grace_period_rejects_negative() -> None:
    """Test that grace period validation rejects negative values."""
    with pytest.raises(ValueError):
        HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            checkout_grace_minutes=-1,
        )


def test_grace_period_rejects_over_30() -> None:
    """Test that grace period validation rejects values over 30."""
    with pytest.raises(ValueError):
        HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            checkout_grace_minutes=31,
        )


def test_identifier_attr_enum_values() -> None:
    """Test IdentifierAttr enum values."""
    assert IdentifierAttr.SLOT_CODE.value == "slot_code"
    assert IdentifierAttr.SLOT_NAME.value == "slot_name"
    assert IdentifierAttr.LAST_FOUR.value == "last_four"


def test_stale_count_non_negative() -> None:
    """Test that stale_count validation rejects negative values."""
    with pytest.raises(ValueError):
        HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            stale_count=-1,
        )
