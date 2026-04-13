# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for admin integration VLAN API endpoints (US2).

Tests T025-T030: CRUD operations with allowed_vlans field.
"""

import pytest
from uuid import uuid4

from pydantic import ValidationError

from captive_portal.api.routes.integrations import (
    IntegrationConfigCreate,
    IntegrationConfigUpdate,
    IntegrationConfigResponse,
)
from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


class TestCreateIntegrationWithVlans:
    """T025: POST with allowed_vlans creates integration with VLANs."""

    def test_create_with_vlans(self) -> None:
        """Create schema accepts allowed_vlans field."""
        schema = IntegrationConfigCreate(
            integration_id="unit_a",
            allowed_vlans=[50, 51],
        )
        assert schema.allowed_vlans == [50, 51]

    def test_create_without_vlans_defaults_empty(self) -> None:
        """Create schema defaults allowed_vlans to empty list."""
        schema = IntegrationConfigCreate(
            integration_id="unit_a",
        )
        assert schema.allowed_vlans == []

    def test_create_with_none_vlans_coerced_empty(self) -> None:
        """Create schema coerces None to empty list."""
        schema = IntegrationConfigCreate(
            integration_id="unit_a",
            allowed_vlans=None,
        )
        assert schema.allowed_vlans == []


class TestUpdateIntegrationVlans:
    """T026: PATCH with allowed_vlans updates the list."""

    def test_update_with_vlans(self) -> None:
        """Update schema accepts allowed_vlans field."""
        schema = IntegrationConfigUpdate(
            allowed_vlans=[50, 55],
        )
        assert schema.allowed_vlans == [50, 55]

    def test_update_omitting_vlans_is_none(self) -> None:
        """Omitting allowed_vlans leaves existing VLANs unchanged."""
        schema = IntegrationConfigUpdate(
            checkout_grace_minutes=20,
        )
        assert schema.allowed_vlans is None

    def test_update_empty_list_removes_restrictions(self) -> None:
        """Setting allowed_vlans to [] removes restrictions."""
        schema = IntegrationConfigUpdate(
            allowed_vlans=[],
        )
        assert schema.allowed_vlans == []


class TestGetIntegrationResponse:
    """T027: GET response includes allowed_vlans field."""

    def test_response_includes_vlans(self) -> None:
        """Response schema includes allowed_vlans field."""
        config_id = uuid4()
        response = IntegrationConfigResponse(
            id=config_id,
            integration_id="unit_a",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
            stale_count=0,
            allowed_vlans=[50, 51],
        )
        assert response.allowed_vlans == [50, 51]

    def test_response_null_vlans_coerced_to_empty(self) -> None:
        """Response schema coerces None to empty list."""
        config_id = uuid4()
        response = IntegrationConfigResponse(
            id=config_id,
            integration_id="unit_a",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
            stale_count=0,
            allowed_vlans=None,
        )
        assert response.allowed_vlans == []

    def test_response_from_model(self) -> None:
        """Response schema works with from_attributes from model."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50, 51],
        )
        response = IntegrationConfigResponse.model_validate(config)
        assert response.allowed_vlans == [50, 51]


class TestInvalidVlanValues:
    """T028: Invalid VLAN values return 422."""

    def test_negative_vlan_rejected(self) -> None:
        """Negative VLAN ID rejected."""
        with pytest.raises(ValidationError):
            IntegrationConfigCreate(
                integration_id="unit_a",
                allowed_vlans=[-1],
            )

    def test_zero_vlan_rejected(self) -> None:
        """VLAN ID 0 rejected."""
        with pytest.raises(ValidationError):
            IntegrationConfigCreate(
                integration_id="unit_a",
                allowed_vlans=[0],
            )

    def test_4095_vlan_rejected(self) -> None:
        """VLAN ID 4095 rejected (above range)."""
        with pytest.raises(ValidationError):
            IntegrationConfigCreate(
                integration_id="unit_a",
                allowed_vlans=[4095],
            )

    def test_text_vlan_rejected(self) -> None:
        """Non-integer VLAN value rejected."""
        with pytest.raises(ValidationError):
            IntegrationConfigCreate(
                integration_id="unit_a",
                allowed_vlans=["abc"],
            )


class TestVlanDeduplicationAndSort:
    """T029: Duplicate VLANs deduplicated and sorted."""

    def test_create_deduplicates_and_sorts(self) -> None:
        """Create schema deduplicates and sorts VLANs."""
        schema = IntegrationConfigCreate(
            integration_id="unit_a",
            allowed_vlans=[55, 50, 50, 51],
        )
        assert schema.allowed_vlans == [50, 51, 55]

    def test_update_deduplicates_and_sorts(self) -> None:
        """Update schema deduplicates and sorts VLANs."""
        schema = IntegrationConfigUpdate(
            allowed_vlans=[55, 50, 50],
        )
        assert schema.allowed_vlans == [50, 55]


class TestCrossIntegrationVlans:
    """T030: Same VLAN on multiple integrations accepted."""

    def test_same_vlan_multiple_integrations(self) -> None:
        """Same VLAN ID can be assigned to multiple integrations."""
        config_a = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        config_b = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_b",
            allowed_vlans=[50],
        )
        assert config_a.allowed_vlans == [50]
        assert config_b.allowed_vlans == [50]
