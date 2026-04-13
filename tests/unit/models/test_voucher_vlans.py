# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Voucher.allowed_vlans field validator (T010)."""

import pytest

from captive_portal.models.voucher import Voucher


class TestVoucherAllowedVlans:
    """Tests for Voucher.allowed_vlans field validation."""

    def test_none_input_accepted(self) -> None:
        """None input for allowed_vlans is accepted (unrestricted)."""
        voucher = Voucher(
            code="TESTVOUCHER1",
            duration_minutes=60,
            allowed_vlans=None,
        )
        assert voucher.allowed_vlans is None

    def test_valid_vlans_accepted(self) -> None:
        """Valid VLAN list is accepted and stored."""
        voucher = Voucher(
            code="TESTVOUCHER2",
            duration_minutes=60,
            allowed_vlans=[50, 51],
        )
        assert voucher.allowed_vlans == [50, 51]

    def test_minimum_vlan_1(self) -> None:
        """VLAN ID 1 (minimum) is accepted."""
        voucher = Voucher(
            code="TESTVOUCHER3",
            duration_minutes=60,
            allowed_vlans=[1],
        )
        assert voucher.allowed_vlans == [1]

    def test_maximum_vlan_4094(self) -> None:
        """VLAN ID 4094 (maximum) is accepted."""
        voucher = Voucher(
            code="TESTVOUCHER4",
            duration_minutes=60,
            allowed_vlans=[4094],
        )
        assert voucher.allowed_vlans == [4094]

    def test_out_of_range_zero_rejected(self) -> None:
        """VLAN ID 0 is rejected (below range)."""
        with pytest.raises(ValueError, match="between 1 and 4094"):
            Voucher(
                code="TESTVOUCHER5",
                duration_minutes=60,
                allowed_vlans=[0],
            )

    def test_out_of_range_4095_rejected(self) -> None:
        """VLAN ID 4095 is rejected (above range)."""
        with pytest.raises(ValueError, match="between 1 and 4094"):
            Voucher(
                code="TESTVOUCHER6",
                duration_minutes=60,
                allowed_vlans=[4095],
            )

    def test_out_of_range_negative_rejected(self) -> None:
        """Negative VLAN ID is rejected."""
        with pytest.raises(ValueError, match="between 1 and 4094"):
            Voucher(
                code="TESTVOUCHER7",
                duration_minutes=60,
                allowed_vlans=[-5],
            )

    def test_duplicate_removal(self) -> None:
        """Duplicate VLAN IDs are silently deduplicated."""
        voucher = Voucher(
            code="TESTVOUCHER8",
            duration_minutes=60,
            allowed_vlans=[50, 50, 51, 51],
        )
        assert voucher.allowed_vlans == [50, 51]

    def test_sort_ordering(self) -> None:
        """VLAN IDs are sorted ascending."""
        voucher = Voucher(
            code="TESTVOUCHER9",
            duration_minutes=60,
            allowed_vlans=[55, 50, 51],
        )
        assert voucher.allowed_vlans == [50, 51, 55]

    def test_default_is_none(self) -> None:
        """Default value for allowed_vlans is None when omitted."""
        voucher = Voucher(
            code="TESTVOUCHERA",
            duration_minutes=60,
        )
        assert voucher.allowed_vlans is None

    def test_empty_list_accepted(self) -> None:
        """Empty list treated as valid (no restrictions)."""
        voucher = Voucher(
            code="TESTVOUCHERB",
            duration_minutes=60,
            allowed_vlans=[],
        )
        assert voucher.allowed_vlans == []
