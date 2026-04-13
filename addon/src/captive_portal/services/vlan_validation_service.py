# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""VLAN validation service for authorization isolation."""

from dataclasses import dataclass

from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher


@dataclass(frozen=True)
class VlanValidationResult:
    """Immutable result of a VLAN validation check.

    Attributes:
        allowed: Whether the device is permitted to authorize.
        reason: Machine-readable reason code
            ("allowed", "skipped", "vlan_mismatch", "missing_vid").
        device_vid: Parsed device VLAN ID (None if unparseable).
        allowed_vlans: The entity's configured VLAN allowlist.
    """

    allowed: bool
    reason: str
    device_vid: int | None
    allowed_vlans: list[int]


class VlanValidationService:
    """Stateless service for VLAN authorization isolation.

    Determines whether a device's VLAN ID is authorized for a given
    integration or voucher. This is the single enforcement point for
    all VLAN isolation logic.
    """

    @staticmethod
    def parse_vid(vid_raw: str | None) -> int | None:
        """Parse and validate a raw VID string.

        Args:
            vid_raw: Raw VID from Omada redirect. May be None, empty,
                non-numeric, or out of IEEE 802.1Q range.

        Returns:
            Integer VLAN ID (1-4094) or None if invalid/missing.
        """
        if vid_raw is None:
            return None
        stripped = vid_raw.strip()
        if not stripped:
            return None
        try:
            vid = int(stripped)
        except ValueError:
            return None
        if vid < 1 or vid > 4094:
            return None
        return vid

    def _validate_vlan(
        self,
        vid_raw: str | None,
        allowed_vlans: list[int] | None,
    ) -> VlanValidationResult:
        """Core VLAN validation logic shared by booking and voucher paths.

        Args:
            vid_raw: Raw VID string from Omada controller redirect.
            allowed_vlans: The entity's configured VLAN allowlist.

        Returns:
            VlanValidationResult with allowed=True/False and reason.
        """
        effective_vlans = allowed_vlans or []

        if not effective_vlans:
            return VlanValidationResult(
                allowed=True,
                reason="skipped",
                device_vid=self.parse_vid(vid_raw),
                allowed_vlans=effective_vlans,
            )

        device_vid = self.parse_vid(vid_raw)
        if device_vid is None:
            return VlanValidationResult(
                allowed=False,
                reason="missing_vid",
                device_vid=None,
                allowed_vlans=effective_vlans,
            )

        if device_vid in effective_vlans:
            return VlanValidationResult(
                allowed=True,
                reason="allowed",
                device_vid=device_vid,
                allowed_vlans=effective_vlans,
            )

        return VlanValidationResult(
            allowed=False,
            reason="vlan_mismatch",
            device_vid=device_vid,
            allowed_vlans=effective_vlans,
        )

    def validate_booking_vlan(
        self,
        vid_raw: str | None,
        integration: HAIntegrationConfig,
    ) -> VlanValidationResult:
        """Validate device VLAN against an integration's allowlist.

        Args:
            vid_raw: Raw VID string from Omada controller redirect.
            integration: The integration whose booking event matched.

        Returns:
            VlanValidationResult with allowed=True/False and reason.
        """
        return self._validate_vlan(vid_raw, integration.allowed_vlans)

    def validate_voucher_vlan(
        self,
        vid_raw: str | None,
        voucher: Voucher,
    ) -> VlanValidationResult:
        """Validate device VLAN against a voucher's allowlist.

        Args:
            vid_raw: Raw VID string from Omada controller redirect.
            voucher: The voucher being redeemed.

        Returns:
            VlanValidationResult with allowed=True/False and reason.
        """
        return self._validate_vlan(vid_raw, voucher.allowed_vlans)
