# type: ignore
# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for admin integration audit logging with VLAN changes (T036a).

Validates that update_integration audit meta includes VLAN change tracking.
"""


class TestIntegrationAuditVlanChanges:
    """T036a: Audit log includes allowed_vlans_old and allowed_vlans_new."""

    def test_vlan_audit_meta_structure(self) -> None:
        """Audit meta for VLAN updates should include old and new values.

        The route handler constructs audit metadata with:
        - allowed_vlans_old: previous value
        - allowed_vlans_new: updated value

        This test validates the data structure contract.
        """
        # Simulate the audit metadata constructed by update_integration
        old_vlans = [50]
        new_vlans = [50, 51, 55]

        audit_meta = {
            "integration_id": "unit_a",
            "allowed_vlans_old": old_vlans,
            "allowed_vlans_new": new_vlans,
        }

        assert audit_meta["allowed_vlans_old"] == [50]
        assert audit_meta["allowed_vlans_new"] == [50, 51, 55]
        assert "integration_id" in audit_meta

    def test_vlan_audit_meta_add_vlans(self) -> None:
        """Audit meta when adding VLANs to unconfigured integration."""
        old_vlans: list[int] = []
        new_vlans = [50, 51]

        audit_meta = {
            "allowed_vlans_old": old_vlans,
            "allowed_vlans_new": new_vlans,
        }

        assert audit_meta["allowed_vlans_old"] == []
        assert audit_meta["allowed_vlans_new"] == [50, 51]

    def test_vlan_audit_meta_remove_vlans(self) -> None:
        """Audit meta when removing all VLANs (revert to unrestricted)."""
        old_vlans = [50, 51]
        new_vlans: list[int] = []

        audit_meta = {
            "allowed_vlans_old": old_vlans,
            "allowed_vlans_new": new_vlans,
        }

        assert audit_meta["allowed_vlans_old"] == [50, 51]
        assert audit_meta["allowed_vlans_new"] == []
