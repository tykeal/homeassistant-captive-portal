# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for HAIntegrationConfig.allowed_vlans field validator (T009)."""

import pytest
from uuid import uuid4

from captive_portal.models.ha_integration_config import HAIntegrationConfig


class TestHAIntegrationConfigAllowedVlans:
    """Tests for HAIntegrationConfig.allowed_vlans field validation."""

    def test_none_input_accepted(self) -> None:
        """None input for allowed_vlans is accepted (unrestricted)."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=None,
        )
        assert config.allowed_vlans is None

    def test_empty_list_accepted(self) -> None:
        """Empty list for allowed_vlans is accepted (unrestricted)."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[],
        )
        assert config.allowed_vlans == []

    def test_valid_single_vlan(self) -> None:
        """Single valid VLAN ID is accepted."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[50],
        )
        assert config.allowed_vlans == [50]

    def test_valid_multiple_vlans(self) -> None:
        """Multiple valid VLAN IDs are accepted."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[50, 51, 55],
        )
        assert config.allowed_vlans == [50, 51, 55]

    def test_minimum_vlan_1(self) -> None:
        """VLAN ID 1 (minimum) is accepted."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[1],
        )
        assert config.allowed_vlans == [1]

    def test_maximum_vlan_4094(self) -> None:
        """VLAN ID 4094 (maximum) is accepted."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[4094],
        )
        assert config.allowed_vlans == [4094]

    def test_out_of_range_zero_rejected(self) -> None:
        """VLAN ID 0 is rejected (below range)."""
        with pytest.raises(ValueError, match="between 1 and 4094"):
            HAIntegrationConfig(
                id=uuid4(),
                integration_id="test",
                allowed_vlans=[0],
            )

    def test_out_of_range_4095_rejected(self) -> None:
        """VLAN ID 4095 is rejected (above range)."""
        with pytest.raises(ValueError, match="between 1 and 4094"):
            HAIntegrationConfig(
                id=uuid4(),
                integration_id="test",
                allowed_vlans=[4095],
            )

    def test_out_of_range_negative_rejected(self) -> None:
        """Negative VLAN ID is rejected."""
        with pytest.raises(ValueError, match="between 1 and 4094"):
            HAIntegrationConfig(
                id=uuid4(),
                integration_id="test",
                allowed_vlans=[-1],
            )

    def test_duplicate_removal(self) -> None:
        """Duplicate VLAN IDs are silently deduplicated."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[50, 50, 51, 51],
        )
        assert config.allowed_vlans == [50, 51]

    def test_sort_ordering(self) -> None:
        """VLAN IDs are sorted ascending."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[55, 50, 51],
        )
        assert config.allowed_vlans == [50, 51, 55]

    def test_duplicate_and_sort_combined(self) -> None:
        """Duplicates removed and result sorted ascending."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
            allowed_vlans=[55, 50, 55, 51, 50],
        )
        assert config.allowed_vlans == [50, 51, 55]

    def test_default_is_none(self) -> None:
        """Default value for allowed_vlans is None."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test",
        )
        assert config.allowed_vlans is None
