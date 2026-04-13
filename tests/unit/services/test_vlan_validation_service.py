# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for VlanValidationService."""

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher
from captive_portal.services.vlan_validation_service import (
    VlanValidationService,
)
from uuid import uuid4


# ── T006: parse_vid tests ──────────────────────────────────────────


class TestParseVid:
    """Tests for VlanValidationService.parse_vid()."""

    def test_none_returns_none(self) -> None:
        """parse_vid(None) returns None."""
        assert VlanValidationService.parse_vid(None) is None

    def test_empty_string_returns_none(self) -> None:
        """parse_vid('') returns None."""
        assert VlanValidationService.parse_vid("") is None

    def test_whitespace_returns_none(self) -> None:
        """parse_vid('   ') returns None."""
        assert VlanValidationService.parse_vid("   ") is None

    def test_valid_int_returns_int(self) -> None:
        """parse_vid('50') returns 50."""
        assert VlanValidationService.parse_vid("50") == 50

    def test_valid_int_1(self) -> None:
        """parse_vid('1') returns 1 (minimum valid VLAN)."""
        assert VlanValidationService.parse_vid("1") == 1

    def test_valid_int_4094(self) -> None:
        """parse_vid('4094') returns 4094 (maximum valid VLAN)."""
        assert VlanValidationService.parse_vid("4094") == 4094

    def test_non_numeric_returns_none(self) -> None:
        """parse_vid('abc') returns None."""
        assert VlanValidationService.parse_vid("abc") is None

    def test_mixed_alphanumeric_returns_none(self) -> None:
        """parse_vid('50a') returns None."""
        assert VlanValidationService.parse_vid("50a") is None

    def test_zero_returns_none(self) -> None:
        """parse_vid('0') returns None (below range)."""
        assert VlanValidationService.parse_vid("0") is None

    def test_4095_returns_none(self) -> None:
        """parse_vid('4095') returns None (above range)."""
        assert VlanValidationService.parse_vid("4095") is None

    def test_negative_returns_none(self) -> None:
        """parse_vid('-1') returns None (below range)."""
        assert VlanValidationService.parse_vid("-1") is None

    def test_float_returns_none(self) -> None:
        """parse_vid('50.5') returns None (non-integer)."""
        assert VlanValidationService.parse_vid("50.5") is None

    def test_large_number_returns_none(self) -> None:
        """parse_vid('99999') returns None (above range)."""
        assert VlanValidationService.parse_vid("99999") is None

    def test_whitespace_padded_valid(self) -> None:
        """parse_vid(' 50 ') returns 50 (strips whitespace)."""
        assert VlanValidationService.parse_vid(" 50 ") == 50


# ── T007: validate_booking_vlan tests ──────────────────────────────


class TestValidateBookingVlan:
    """Tests for VlanValidationService.validate_booking_vlan()."""

    def setup_method(self) -> None:
        """Create service instance for each test."""
        self.svc = VlanValidationService()

    def _make_integration(self, vlans: list[int] | None = None) -> HAIntegrationConfig:
        """Create test integration config with optional VLANs."""
        return HAIntegrationConfig(
            id=uuid4(),
            integration_id="test_integration",
            allowed_vlans=vlans,
        )

    def test_no_vlans_configured_skips(self) -> None:
        """No VLANs configured → allowed=True, reason='skipped'."""
        integration = self._make_integration(vlans=None)
        result = self.svc.validate_booking_vlan("50", integration)
        assert result.allowed is True
        assert result.reason == "skipped"

    def test_empty_vlans_list_skips(self) -> None:
        """Empty VLANs list → allowed=True, reason='skipped'."""
        integration = self._make_integration(vlans=[])
        result = self.svc.validate_booking_vlan("50", integration)
        assert result.allowed is True
        assert result.reason == "skipped"

    def test_matching_vid_allowed(self) -> None:
        """Matching VID → allowed=True, reason='allowed'."""
        integration = self._make_integration(vlans=[50, 51])
        result = self.svc.validate_booking_vlan("50", integration)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.device_vid == 50
        assert result.allowed_vlans == [50, 51]

    def test_non_matching_vid_rejected(self) -> None:
        """Non-matching VID → allowed=False, reason='vlan_mismatch'."""
        integration = self._make_integration(vlans=[50, 51])
        result = self.svc.validate_booking_vlan("52", integration)
        assert result.allowed is False
        assert result.reason == "vlan_mismatch"
        assert result.device_vid == 52

    def test_missing_vid_with_vlans_configured(self) -> None:
        """Missing VID with VLANs configured → allowed=False, reason='missing_vid'."""
        integration = self._make_integration(vlans=[50, 51])
        result = self.svc.validate_booking_vlan(None, integration)
        assert result.allowed is False
        assert result.reason == "missing_vid"
        assert result.device_vid is None

    def test_empty_vid_with_vlans_configured(self) -> None:
        """Empty VID with VLANs configured → allowed=False, reason='missing_vid'."""
        integration = self._make_integration(vlans=[50, 51])
        result = self.svc.validate_booking_vlan("", integration)
        assert result.allowed is False
        assert result.reason == "missing_vid"

    def test_invalid_vid_with_vlans_configured(self) -> None:
        """Non-numeric VID with VLANs configured → allowed=False, reason='missing_vid'."""
        integration = self._make_integration(vlans=[50, 51])
        result = self.svc.validate_booking_vlan("abc", integration)
        assert result.allowed is False
        assert result.reason == "missing_vid"

    def test_multiple_allowed_vlans_any_match(self) -> None:
        """Multiple VLANs configured, VID matches second → allowed=True."""
        integration = self._make_integration(vlans=[50, 51, 55])
        result = self.svc.validate_booking_vlan("55", integration)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.device_vid == 55

    def test_result_includes_allowed_vlans(self) -> None:
        """Result always includes the entity's configured allowlist."""
        integration = self._make_integration(vlans=[50, 51])
        result = self.svc.validate_booking_vlan("50", integration)
        assert result.allowed_vlans == [50, 51]

    def test_out_of_range_vid_treated_as_missing(self) -> None:
        """Out-of-range VID (4095) treated as missing."""
        integration = self._make_integration(vlans=[50])
        result = self.svc.validate_booking_vlan("4095", integration)
        assert result.allowed is False
        assert result.reason == "missing_vid"


# ── T008: validate_voucher_vlan tests ──────────────────────────────


class TestValidateVoucherVlan:
    """Tests for VlanValidationService.validate_voucher_vlan()."""

    def setup_method(self) -> None:
        """Create service instance for each test."""
        self.svc = VlanValidationService()

    def _make_voucher(self, vlans: list[int] | None = None) -> Voucher:
        """Create test voucher with optional VLANs."""
        return Voucher(
            code="TESTVOUCHER1",
            duration_minutes=60,
            allowed_vlans=vlans,
        )

    def test_none_allowlist_skips(self) -> None:
        """None allowlist → allowed=True, reason='skipped' (unrestricted)."""
        voucher = self._make_voucher(vlans=None)
        result = self.svc.validate_voucher_vlan("50", voucher)
        assert result.allowed is True
        assert result.reason == "skipped"

    def test_matching_vid_allowed(self) -> None:
        """Matching VID → allowed=True, reason='allowed'."""
        voucher = self._make_voucher(vlans=[50, 51])
        result = self.svc.validate_voucher_vlan("50", voucher)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.device_vid == 50

    def test_non_matching_vid_rejected(self) -> None:
        """Non-matching VID → allowed=False, reason='vlan_mismatch'."""
        voucher = self._make_voucher(vlans=[50, 51])
        result = self.svc.validate_voucher_vlan("52", voucher)
        assert result.allowed is False
        assert result.reason == "vlan_mismatch"
        assert result.device_vid == 52

    def test_missing_vid_with_vlans_configured(self) -> None:
        """Missing VID with VLANs configured → allowed=False, reason='missing_vid'."""
        voucher = self._make_voucher(vlans=[50])
        result = self.svc.validate_voucher_vlan(None, voucher)
        assert result.allowed is False
        assert result.reason == "missing_vid"
        assert result.device_vid is None

    def test_empty_vlans_list_skips(self) -> None:
        """Empty VLANs list → skipped (treated like unrestricted)."""
        voucher = self._make_voucher(vlans=[])
        result = self.svc.validate_voucher_vlan("50", voucher)
        assert result.allowed is True
        assert result.reason == "skipped"
