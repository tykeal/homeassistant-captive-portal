# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""TP-Omada controller adapter for grant authorization and revocation."""

import math
from datetime import datetime, timezone
from typing import Any, Optional

from captive_portal.controllers.tp_omada.base_client import (
    OmadaClient,
    OmadaClientError,
)


class OmadaAdapter:
    """Adapter for TP-Omada controller operations (authorize, revoke, update).

    Attributes:
        client: OmadaClient instance for HTTP communication
        site_id: Omada site identifier (e.g., "Default")
    """

    def __init__(self, client: OmadaClient, site_id: str = "Default") -> None:
        """Initialize Omada adapter.

        Args:
            client: Initialized OmadaClient
            site_id: Omada site identifier (default: "Default")
        """
        self.client = client
        self.site_id = site_id

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
        """Authorize device on controller with expiration time.

        Builds the payload conditionally for Gateway or EAP auth:
        - Gateway auth: includes ``gatewayMac`` and ``vid``
        - EAP auth: includes ``apMac``, ``ssidName``, ``radioId``

        The ``expires_at`` timestamp is converted to an authorization
        duration in seconds (relative to now) for the Omada payload.

        Args:
            mac: Device MAC address (AA:BB:CC:DD:EE:FF format)
            expires_at: Grant expiration timestamp (UTC).
                Converted to a duration in seconds for the
                controller.
            upload_limit_kbps: Upload bandwidth limit in kbps (0 = unlimited)
            download_limit_kbps: Download bandwidth limit in kbps (0 = unlimited)
            gateway_mac: Gateway MAC for Gateway auth mode
            ap_mac: Access point MAC for EAP auth mode
            ssid_name: SSID name for EAP auth mode
            radio_id: Radio identifier for EAP auth mode
            vid: VLAN ID for Gateway auth mode

        Returns:
            dict with keys:
                - grant_id: Controller-assigned grant identifier
                - status: Grant status ("active" or "pending")
                - mac: Echo of authorized MAC

        Raises:
            OmadaClientError: On controller errors
            OmadaRetryExhaustedError: If retries exhausted
        """
        # Calculate authorization duration in seconds
        now = datetime.now(timezone.utc)
        expires_at_utc = (
            expires_at.replace(tzinfo=timezone.utc)
            if expires_at.tzinfo is None
            else expires_at.astimezone(timezone.utc)
        )
        duration_seconds = max(math.ceil((expires_at_utc - now).total_seconds()), 0)

        payload: dict[str, Any] = {
            "clientMac": mac,
            "site": self.site_id,
            "time": duration_seconds,
            "authType": 4,  # External portal auth type
        }

        # Gateway auth mode (takes precedence over EAP)
        if gateway_mac:
            payload["gatewayMac"] = gateway_mac
            payload["vid"] = vid or ""
        elif ap_mac:
            # EAP auth mode
            payload["apMac"] = ap_mac
            if ssid_name:
                payload["ssidName"] = ssid_name
            if radio_id:
                payload["radioId"] = radio_id

        # Only include bandwidth limits when non-zero
        if upload_limit_kbps:
            payload["upKbps"] = upload_limit_kbps
        if download_limit_kbps:
            payload["downKbps"] = download_limit_kbps

        # Call controller authorize endpoint with retry
        endpoint = f"/{self.client.controller_id}/api/v2/hotspot/extPortal/auth"
        response = await self.client.post_with_retry(endpoint, payload)

        # Extract result
        result = response.get("result", {})
        return {
            "grant_id": result.get("clientId", mac),  # Use MAC as fallback ID
            "status": "active" if result.get("authorized") else "pending",
            "mac": mac,
        }

    async def revoke(self, mac: str, grant_id: Optional[str] = None) -> dict[str, Any]:
        """Revoke device authorization on controller.

        Args:
            mac: Device MAC address
            grant_id: Optional controller grant ID (unused, for signature compatibility)

        Returns:
            dict with keys:
                - success: Whether revoke succeeded
                - mac: Echo of revoked MAC

        Raises:
            OmadaClientError: On controller errors (except 404 not found)
            OmadaRetryExhaustedError: If retries exhausted
        """
        payload = {
            "clientMac": mac,
            "site": self.site_id,
        }

        try:
            endpoint = f"/{self.client.controller_id}/api/v2/hotspot/extPortal/revoke"
            await self.client.post_with_retry(endpoint, payload)
            return {"success": True, "mac": mac}
        except OmadaClientError as e:
            # Treat 404 as success (already revoked/not found)
            if hasattr(e, "status_code") and e.status_code == 404:
                return {"success": True, "mac": mac, "note": "Already revoked"}
            raise

    async def update(
        self, mac: str, expires_at: datetime, grant_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Update existing grant expiration time.

        Args:
            mac: Device MAC address
            expires_at: New expiration timestamp (UTC)
            grant_id: Optional controller grant ID (unused, for signature compatibility)

        Returns:
            dict with updated grant info

        Raises:
            OmadaClientError: On controller errors
        """
        # TP-Omada typically requires re-authorization to extend
        # (no separate update endpoint documented)
        return await self.authorize(mac, expires_at)

    async def get_status(self, mac: str) -> dict[str, Any]:
        """Get current authorization status for device.

        Args:
            mac: Device MAC address

        Returns:
            dict with keys:
                - mac: Device MAC
                - authorized: Whether currently authorized
                - remaining_seconds: Optional remaining time (if available)

        Note:
            This uses the ``/{controller_id}/api/v2/hotspot/extPortal/session``
            endpoint.  May not be supported by all Omada versions.
        """
        payload = {"clientMac": mac, "site": self.site_id}

        try:
            endpoint = f"/{self.client.controller_id}/api/v2/hotspot/extPortal/session"
            response = await self.client.post_with_retry(endpoint, payload)
            result = response.get("result", {})
            return {
                "mac": mac,
                "authorized": result.get("authorized", False),
                "remaining_seconds": result.get("remainingTime", 0),
            }
        except Exception:
            # Session endpoint may not exist on all versions
            return {"mac": mac, "authorized": False, "remaining_seconds": 0}
