# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""TP-Omada controller adapter for grant authorization and revocation."""

from datetime import datetime
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
    ) -> dict[str, Any]:
        """Authorize device on controller with expiration time.

        Args:
            mac: Device MAC address (AA:BB:CC:DD:EE:FF format)
            expires_at: Grant expiration timestamp (UTC)
            upload_limit_kbps: Upload bandwidth limit in kbps (0 = unlimited)
            download_limit_kbps: Download bandwidth limit in kbps (0 = unlimited)

        Returns:
            dict with keys:
                - grant_id: Controller-assigned grant identifier
                - status: Grant status ("active" or "pending")
                - mac: Echo of authorized MAC

        Raises:
            OmadaClientError: On controller errors
            OmadaRetryExhaustedError: If retries exhausted
        """
        # Convert datetime to microseconds since epoch
        time_micros = int(expires_at.timestamp() * 1_000_000)

        payload = {
            "clientMac": mac,
            "site": self.site_id,
            "time": time_micros,
            "authType": 4,  # External portal auth type
            "upKbps": upload_limit_kbps,
            "downKbps": download_limit_kbps,
        }

        # Call controller authorize endpoint with retry
        response = await self.client.post_with_retry("/extportal/auth", payload)

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
            await self.client.post_with_retry("/extportal/revoke", payload)
            return {"success": True, "mac": mac}
        except OmadaClientError as e:
            # Log but don't fail on 404 (already revoked/not found)
            if e.status_code == 404:
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
            This uses the optional /extportal/session endpoint if available.
            May not be supported by all Omada versions.
        """
        payload = {"clientMac": mac, "site": self.site_id}

        try:
            response = await self.client.post_with_retry("/extportal/session", payload)
            result = response.get("result", {})
            return {
                "mac": mac,
                "authorized": result.get("authorized", False),
                "remaining_seconds": result.get("remainingTime", 0),
            }
        except Exception:
            # Session endpoint may not exist on all versions
            return {"mac": mac, "authorized": False, "remaining_seconds": 0}
