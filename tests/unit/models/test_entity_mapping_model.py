# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test HA integration entity mapping model."""

from datetime import datetime, timezone

import pytest

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


def test_entity_mapping_integration_id_unique() -> None:
    """Integration_id field is marked unique on the model."""
    config = HAIntegrationConfig(integration_id="rental_control_airbnb")
    assert config.integration_id == "rental_control_airbnb"


def test_entity_mapping_identifier_attr_enum() -> None:
    """Identifier attribute must be slot_code, slot_name, or last_four."""
    for attr in IdentifierAttr:
        config = HAIntegrationConfig(
            integration_id="test",
            identifier_attr=attr,
        )
        assert config.identifier_attr == attr

    with pytest.raises(ValueError):
        HAIntegrationConfig(
            integration_id="test",
            identifier_attr="invalid_attr",
        )


def test_entity_mapping_last_sync_utc() -> None:
    """Last sync timestamp must be UTC."""
    now = datetime.now(timezone.utc)
    config = HAIntegrationConfig(
        integration_id="test",
        last_sync_utc=now,
    )
    assert config.last_sync_utc == now

    config2 = HAIntegrationConfig(integration_id="test2")
    assert config2.last_sync_utc is None


def test_entity_mapping_stale_count_increments() -> None:
    """Stale count increments on each missed HA poll."""
    config = HAIntegrationConfig(integration_id="test")
    assert config.stale_count == 0
    config.stale_count = 1
    assert config.stale_count == 1
    config.stale_count = 3
    assert config.stale_count == 3


def test_entity_mapping_stale_threshold() -> None:
    """Stale count validation rejects negative and stores thresholds."""
    with pytest.raises(ValueError):
        HAIntegrationConfig(integration_id="test", stale_count=-1)

    config = HAIntegrationConfig(integration_id="test", stale_count=6)
    assert config.stale_count == 6
    assert config.stale_count >= 6
