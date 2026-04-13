# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for VLAN scoping during voucher authorization (US3).

Tests T038-T042: voucher VLAN restriction during redemption.
"""

import pytest

from captive_portal.models.voucher import Voucher
from captive_portal.services.vlan_validation_service import VlanValidationService


class TestVoucherUnrestricted:
    """T038: Unrestricted voucher redeemable from any VLAN."""

    @pytest.mark.parametrize("vid_raw", [None, "", "50", "99", "abc"])
    def test_no_vlans_voucher_skips_validation(self, vid_raw: str | None) -> None:
        """Voucher with None allowed_vlans is redeemable from any VLAN."""
        svc = VlanValidationService()
        voucher = Voucher(
            code="TESTVOUCHR01",
            duration_minutes=60,
            allowed_vlans=None,
        )
        result = svc.validate_voucher_vlan(vid_raw, voucher)
        assert result.allowed is True
        assert result.reason == "skipped"


class TestVoucherVlanMatch:
    """T039: VLAN-restricted voucher redeemable from matching VID."""

    def test_matching_vid_allowed(self) -> None:
        """Voucher with VLANs [50, 51], device on 50 → allowed."""
        svc = VlanValidationService()
        voucher = Voucher(
            code="TESTVOUCHR02",
            duration_minutes=60,
            allowed_vlans=[50, 51],
        )
        result = svc.validate_voucher_vlan("50", voucher)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.device_vid == 50


class TestVoucherVlanMismatch:
    """T040: VLAN-restricted voucher rejected from non-matching VID."""

    def test_non_matching_vid_rejected(self) -> None:
        """Voucher with VLAN [50], device on 52 → rejected."""
        svc = VlanValidationService()
        voucher = Voucher(
            code="TESTVOUCHR03",
            duration_minutes=60,
            allowed_vlans=[50],
        )
        result = svc.validate_voucher_vlan("52", voucher)
        assert result.allowed is False
        assert result.reason == "vlan_mismatch"
        assert result.device_vid == 52


class TestVoucherVlanMissingVid:
    """T041: VLAN-restricted voucher rejected when VID is missing."""

    @pytest.mark.parametrize("vid_raw", [None, "", "   "])
    def test_missing_vid_rejected(self, vid_raw: str | None) -> None:
        """Voucher with VLANs but no device VID → rejected."""
        svc = VlanValidationService()
        voucher = Voucher(
            code="TESTVOUCHR04",
            duration_minutes=60,
            allowed_vlans=[50],
        )
        result = svc.validate_voucher_vlan(vid_raw, voucher)
        assert result.allowed is False
        assert result.reason == "missing_vid"


class TestVoucherMultiUseVlan:
    """T042: Multi-use voucher with VLAN — each redemption validated."""

    def test_each_redemption_independently_validated(self) -> None:
        """Same voucher: VLAN 50 succeeds, VLAN 52 rejected.

        Each redemption attempt is independently validated against
        the voucher's VLAN restrictions.
        """
        svc = VlanValidationService()
        voucher = Voucher(
            code="TESTVOUCHR05",
            duration_minutes=60,
            allowed_vlans=[50],
        )

        # First attempt: VLAN 50 → allowed
        result1 = svc.validate_voucher_vlan("50", voucher)
        assert result1.allowed is True

        # Second attempt: VLAN 52 → rejected
        result2 = svc.validate_voucher_vlan("52", voucher)
        assert result2.allowed is False
        assert result2.reason == "vlan_mismatch"

        # Third attempt: VLAN 50 again → still allowed
        result3 = svc.validate_voucher_vlan("50", voucher)
        assert result3.allowed is True
