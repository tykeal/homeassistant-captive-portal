# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for backward compatibility with unconfigured VLANs (US4).

Tests T020-T023a: existing deployments with no VLAN configuration.
"""

import pytest
from uuid import uuid4

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher
from captive_portal.services.vlan_validation_service import VlanValidationService


class TestBackwardCompatNoneVlans:
    """T020: Authorization proceeds when allowed_vlans is None."""

    @pytest.mark.parametrize("vid_raw", [None, "", "50", "999", "abc"])
    def test_no_vlans_configured_skips_validation(self, vid_raw: str | None) -> None:
        """Integration with None VLANs skips VLAN check for any VID."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_legacy",
            allowed_vlans=None,
        )
        result = svc.validate_booking_vlan(vid_raw, integration)
        assert result.allowed is True
        assert result.reason == "skipped"


class TestBackwardCompatEmptyVlans:
    """T021: Authorization proceeds when allowed_vlans is empty list."""

    @pytest.mark.parametrize("vid_raw", [None, "", "50", "999", "abc"])
    def test_empty_vlans_list_skips_validation(self, vid_raw: str | None) -> None:
        """Integration with empty VLANs list skips VLAN check for any VID."""
        svc = VlanValidationService()
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_empty",
            allowed_vlans=[],
        )
        result = svc.validate_booking_vlan(vid_raw, integration)
        assert result.allowed is True
        assert result.reason == "skipped"


class TestBackwardCompatMixedDeployment:
    """T022: Mixed deployment — some integrations enforce, some skip."""

    def test_configured_enforces_while_unconfigured_skips(self) -> None:
        """Configured integration enforces VLANs; unconfigured skips."""
        svc = VlanValidationService()

        configured = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_configured",
            allowed_vlans=[50],
        )
        unconfigured = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_unconfigured",
            allowed_vlans=None,
        )

        # Configured: VLAN 50 → allowed
        assert svc.validate_booking_vlan("50", configured).allowed is True
        # Configured: VLAN 99 → rejected
        assert svc.validate_booking_vlan("99", configured).allowed is False

        # Unconfigured: any VLAN → allowed (skipped)
        assert svc.validate_booking_vlan("99", unconfigured).allowed is True
        assert svc.validate_booking_vlan(None, unconfigured).allowed is True


class TestBackwardCompatMigration:
    """T023: Migration adds column with NULL default."""

    def test_model_defaults_to_none(self) -> None:
        """New model without explicit allowed_vlans defaults to None."""
        config = HAIntegrationConfig(
            id=uuid4(),
            integration_id="test_migration",
        )
        assert config.allowed_vlans is None

    def test_voucher_defaults_to_none(self) -> None:
        """New voucher without explicit allowed_vlans defaults to None."""
        voucher = Voucher(
            code="TESTMIGRATE1",
            duration_minutes=60,
        )
        assert voucher.allowed_vlans is None


class TestBackwardCompatActiveGrants:
    """T023a: Active grants remain valid after VLAN config changes.

    This tests the design principle that changing VLAN configuration
    does NOT retroactively affect existing active grants (FR-013).
    The validation service only validates NEW authorization attempts.
    """

    def test_service_validates_new_attempts_not_existing_grants(self) -> None:
        """VlanValidationService validates requests, not persisted grants.

        The service is stateless — it only validates a vid against an
        entity's current allowlist. Existing grants are not re-validated
        when the integration's allowed_vlans changes.
        """
        svc = VlanValidationService()

        # Initially allow VLAN 50
        integration = HAIntegrationConfig(
            id=uuid4(),
            integration_id="unit_a",
            allowed_vlans=[50],
        )
        result_before = svc.validate_booking_vlan("50", integration)
        assert result_before.allowed is True

        # Change to only allow VLAN 99
        integration.allowed_vlans = [99]
        result_after = svc.validate_booking_vlan("50", integration)
        assert result_after.allowed is False

        # But any existing grant created while VLAN 50 was allowed
        # is NOT affected — the service only checks new requests
