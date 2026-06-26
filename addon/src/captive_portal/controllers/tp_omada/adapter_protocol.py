# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Shared TP-Link Omada controller adapter Protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class OmadaControllerAdapter(Protocol):
    """Shared interface for TP-Link Omada controller backends."""

    async def authorize(
        self,
        mac: str,
        expires_at: datetime,
        upload_limit_kbps: int = 0,
        download_limit_kbps: int = 0,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
        vid: str | None = None,
    ) -> dict[str, Any]:
        """Authorize a guest device by MAC.

        Args:
            mac: Guest MAC address in caller-facing format.
            expires_at: Add-on-managed grant expiry timestamp.
            upload_limit_kbps: Optional upload limit for legacy controllers.
            download_limit_kbps: Optional download limit for legacy controllers.
            gateway_mac: Optional legacy Gateway auth-mode MAC context.
            ap_mac: Optional legacy EAP access point MAC context.
            ssid_name: Optional legacy EAP SSID context.
            radio_id: Optional legacy EAP radio identifier.
            vid: Optional legacy Gateway VLAN identifier.

        Returns:
            Controller authorization mapping compatible with existing flows.
        """
        ...

    async def revoke(
        self,
        mac: str,
        grant_id: str | None = None,
        gateway_mac: str | None = None,
        ap_mac: str | None = None,
        vid: str | None = None,
        ssid_name: str | None = None,
        radio_id: str | None = None,
    ) -> dict[str, Any]:
        """Deauthorize a guest device by MAC.

        Args:
            mac: Guest MAC address in caller-facing format.
            grant_id: Optional controller grant identifier.
            gateway_mac: Optional legacy Gateway auth-mode MAC context.
            ap_mac: Optional legacy EAP access point MAC context.
            vid: Optional legacy Gateway VLAN identifier.
            ssid_name: Optional legacy EAP SSID context.
            radio_id: Optional legacy EAP radio identifier.

        Returns:
            Controller revocation mapping compatible with existing flows.
        """
        ...

    async def update(
        self,
        mac: str,
        expires_at: datetime,
        grant_id: str | None = None,
    ) -> dict[str, Any]:
        """Refresh or extend a controller authorization if supported.

        Args:
            mac: Guest MAC address in caller-facing format.
            expires_at: Add-on-managed grant expiry timestamp.
            grant_id: Optional controller grant identifier.

        Returns:
            Controller update mapping compatible with existing flows.
        """
        ...

    async def get_status(self, mac: str) -> dict[str, Any]:
        """Return best-effort authorization status for a MAC.

        Args:
            mac: Guest MAC address in caller-facing format.

        Returns:
            Best-effort authorization status mapping.
        """
        ...
