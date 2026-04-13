# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for VLAN validation during booking authorization (US1).

Tests T011-T015a: booking authorization flow with VLAN isolation.
"""

import pytest
from uuid import uuid4

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.services.vlan_validation_service import VlanValidationService


class TestVlanBookingAuthorizationMatch:
    """T011: Booking authorization succeeds with matching VID."""

    def test_booking_auth_succeeds_matching_vid(self) -> None:
        """Given integration with VLAN 50, device on VLAN 50 → allowed."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        result = svc.validate_booking_vlan("50", integration)
        assert result.allowed is True
        assert result.reason == "allowed"


class TestVlanBookingAuthorizationMismatch:
    """T012: Booking authorization rejected with non-matching VID."""

    def test_booking_auth_rejected_non_matching_vid(self) -> None:
        """Given integration with VLAN 50, device on VLAN 51 → rejected."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        result = svc.validate_booking_vlan("51", integration)
        assert result.allowed is False
        assert result.reason == "vlan_mismatch"

    def test_error_message_does_not_expose_vlan(self) -> None:
        """Error message is vague - does not reveal VLAN IDs."""
        # The route handler returns "This code is not valid for your network."
        # Verify the service result reason is machine-readable, not user-facing
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        result = svc.validate_booking_vlan("51", integration)
        assert "50" not in result.reason
        assert "51" not in result.reason


class TestVlanBookingAuthorizationMissingVid:
    """T013: Booking auth rejected when VID is missing/empty/malformed."""

    @pytest.mark.parametrize(
        "vid_raw",
        [None, "", "   ", "abc", "50.5", "-1", "4095", "0"],
    )
    def test_booking_auth_rejected_missing_vid(self, vid_raw: str | None) -> None:
        """Integration has VLANs but device VID is invalid → rejected."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        result = svc.validate_booking_vlan(vid_raw, integration)
        assert result.allowed is False
        assert result.reason == "missing_vid"


class TestVlanBookingAuthorizationMultipleVlans:
    """T014: Booking auth succeeds when VID matches any allowed VLAN."""

    def test_multiple_vlans_any_match(self) -> None:
        """Integration with VLANs [50, 51, 55], device on 55 → allowed."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50, 51, 55],
        )
        result = svc.validate_booking_vlan("55", integration)
        assert result.allowed is True
        assert result.reason == "allowed"

    def test_multiple_vlans_none_match(self) -> None:
        """Integration with VLANs [50, 51], device on 99 → rejected."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50, 51],
        )
        result = svc.validate_booking_vlan("99", integration)
        assert result.allowed is False
        assert result.reason == "vlan_mismatch"


class TestVlanBookingAuditLog:
    """T015: Audit log includes VLAN validation fields."""

    def test_result_contains_vlan_metadata(self) -> None:
        """Validation result includes device_vid and allowed_vlans."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50, 51],
        )
        result = svc.validate_booking_vlan("50", integration)
        assert result.device_vid == 50
        assert result.allowed_vlans == [50, 51]
        assert result.reason == "allowed"

    def test_mismatch_result_contains_metadata(self) -> None:
        """Mismatch result includes device_vid and allowed_vlans."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50, 51],
        )
        result = svc.validate_booking_vlan("52", integration)
        assert result.device_vid == 52
        assert result.allowed_vlans == [50, 51]
        assert result.reason == "vlan_mismatch"


class TestVlanBookingMultiIntegrationResolution:
    """T015a: Multi-integration VLAN disambiguation."""

    def test_same_code_different_vlans_resolves_correctly(self) -> None:
        """Two integrations with same code - VLAN selects correct one.

        This tests the service-level validation. The route-level multi-
        integration resolution is tested separately in route tests.
        """
        svc = VlanValidationService()

        integration_a = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        integration_b = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_b",
            allowed_vlans=[51],
        )

        # Device on VLAN 50 matches integration_a
        result_a = svc.validate_booking_vlan("50", integration_a)
        result_b = svc.validate_booking_vlan("50", integration_b)
        assert result_a.allowed is True
        assert result_b.allowed is False

        # Device on VLAN 51 matches integration_b
        result_a2 = svc.validate_booking_vlan("51", integration_a)
        result_b2 = svc.validate_booking_vlan("51", integration_b)
        assert result_a2.allowed is False
        assert result_b2.allowed is True
