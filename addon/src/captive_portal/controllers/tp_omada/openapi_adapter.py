# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Omada OpenAPI controller adapter implementation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient

_MAC_PATTERN = re.compile(r"^(?P<octets>[0-9A-Fa-f]{12})$")


def format_openapi_mac(mac: str) -> str:
    """Normalize a MAC address for OpenAPI path parameters.

    Args:
        mac: MAC address in colon, dash, or compact form.

    Returns:
        Uppercase dash-separated MAC address.

    Raises:
        OmadaClientError: If the MAC address is invalid.
    """
    compact = mac.replace(":", "").replace("-", "").strip()
    match = _MAC_PATTERN.match(compact)
    if not match:
        raise OmadaClientError("Invalid MAC address for Omada OpenAPI request")
    octets = match.group("octets").upper()
    return "-".join(octets[index : index + 2] for index in range(0, 12, 2))


def _format_colon_mac(mac: str) -> str:
    """Normalize a MAC address for application-facing responses.

    Args:
        mac: MAC address in accepted input format.

    Returns:
        Uppercase colon-separated MAC address.
    """
    return format_openapi_mac(mac).replace("-", ":")


@dataclass
class OpenApiSiteCache:
    """Shared site discovery cache for an OpenAPI backend run.

    Attributes:
        site_name: Human-readable configured site name.
        site_id: Discovered OpenAPI site ID.
        lock: Async lock guarding single-flight discovery.
    """

    site_name: str
    site_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class OmadaOpenApiAdapter:
    """Controller adapter backed by documented Omada OpenAPI endpoints."""

    def __init__(
        self,
        *,
        client: OpenApiClient,
        site_name: str = "Default",
        site_cache: OpenApiSiteCache | None = None,
    ) -> None:
        """Initialize the OpenAPI adapter.

        Args:
            client: OpenAPI HTTP client.
            site_name: Configured human-readable site name.
            site_cache: Optional shared site cache.
        """
        self.client = client
        self.site_cache = site_cache or OpenApiSiteCache(site_name=site_name)

    async def get_site_id(self) -> str:
        """Return the discovered site ID, using the cache when possible.

        Returns:
            OpenAPI site ID.
        """
        async with self.site_cache.lock:
            if self.site_cache.site_id:
                return self.site_cache.site_id
            self.site_cache.site_id = await self._discover_site_id()
            return self.site_cache.site_id

    async def _discover_site_id(self) -> str:
        """Discover the OpenAPI site ID by configured site name.

        Returns:
            Matching site ID.

        Raises:
            OmadaClientError: If no matching site is found.
        """
        page = 1
        while True:
            payload = await self.client.get(
                f"/openapi/v1/{self.client.controller_id}/sites",
                params={"page": page, "pageSize": 100},
            )
            result = payload.get("result", {})
            for item in result.get("data", []):
                if item.get("name") == self.site_cache.site_name:
                    site_id = item.get("siteId") or item.get("id")
                    if isinstance(site_id, str) and site_id:
                        return site_id
            total_page = int(result.get("totalPage", page))
            if page >= total_page:
                break
            page += 1
        raise OmadaClientError(f"Omada OpenAPI site not found: {self.site_cache.site_name}")

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
        """Authorize a client through the OpenAPI hotspot auth endpoint.

        Args:
            mac: Guest MAC address.
            expires_at: Add-on-managed expiry timestamp; not sent to OpenAPI.
            upload_limit_kbps: Ignored OpenAPI compatibility parameter.
            download_limit_kbps: Ignored OpenAPI compatibility parameter.
            gateway_mac: Ignored legacy compatibility parameter.
            ap_mac: Ignored legacy compatibility parameter.
            ssid_name: Ignored legacy compatibility parameter.
            radio_id: Ignored legacy compatibility parameter.
            vid: Ignored legacy compatibility parameter.

        Returns:
            Existing application-compatible authorization mapping.
        """
        del (
            expires_at,
            upload_limit_kbps,
            download_limit_kbps,
            gateway_mac,
            ap_mac,
            ssid_name,
            radio_id,
            vid,
        )
        path_mac = format_openapi_mac(mac)
        site_id = await self.get_site_id()
        await self.client.post(
            self._hotspot_client_path(site_id, path_mac, "auth"),
        )
        response_mac = path_mac.replace("-", ":")
        return {"grant_id": response_mac, "status": "active", "mac": response_mac}

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
        """Deauthorize a client through the OpenAPI hotspot unauth endpoint.

        Args:
            mac: Guest MAC address.
            grant_id: Ignored compatibility parameter.
            gateway_mac: Ignored legacy compatibility parameter.
            ap_mac: Ignored legacy compatibility parameter.
            vid: Ignored legacy compatibility parameter.
            ssid_name: Ignored legacy compatibility parameter.
            radio_id: Ignored legacy compatibility parameter.

        Returns:
            Existing application-compatible revocation mapping.
        """
        del grant_id, gateway_mac, ap_mac, vid, ssid_name, radio_id
        path_mac = format_openapi_mac(mac)
        site_id = await self.get_site_id()
        try:
            await self.client.post(
                self._hotspot_client_path(site_id, path_mac, "unauth"),
            )
        except OmadaClientError as exc:
            if exc.status_code == 404:
                return {"success": True, "mac": path_mac.replace("-", ":")}
            raise
        return {"success": True, "mac": path_mac.replace("-", ":")}

    async def update(
        self,
        mac: str,
        expires_at: datetime,
        grant_id: str | None = None,
    ) -> dict[str, Any]:
        """Refresh authorization without using undocumented duration fields.

        Args:
            mac: Guest MAC address.
            expires_at: Add-on-managed expiry timestamp.
            grant_id: Optional grant identifier.

        Returns:
            Authorization mapping from ``authorize``.
        """
        del grant_id
        return await self.authorize(mac=mac, expires_at=expires_at)

    async def get_status(self, mac: str) -> dict[str, Any]:
        """Return best-effort authorization status for a MAC.

        Args:
            mac: Guest MAC address.

        Returns:
            Best-effort status mapping.
        """
        path_mac = format_openapi_mac(mac)
        record = await self._find_auth_record(path_mac)
        response_mac = path_mac.replace("-", ":")
        if record is None:
            return {"mac": response_mac, "authorized": False, "remaining_seconds": 0}
        return {
            "mac": response_mac,
            "authorized": bool(record.get("valid", True)),
            "remaining_seconds": self._remaining_seconds(record),
        }

    async def _find_auth_record(self, path_mac: str) -> dict[str, Any] | None:
        """Find an authed-record entry for a normalized OpenAPI MAC.

        Args:
            path_mac: Uppercase dash-separated MAC address.

        Returns:
            Matching record or ``None``.
        """
        page = 1
        site_id = await self.get_site_id()
        while True:
            payload = await self.client.get(
                f"/openapi/v1/{self.client.controller_id}/sites/{site_id}/hotspot/authed-records",
                params={"page": page, "pageSize": 100},
            )
            result = payload.get("result", {})
            for record in result.get("data", []):
                record_mac = str(record.get("mac", ""))
                try:
                    if format_openapi_mac(record_mac) == path_mac:
                        return dict(record)
                except OmadaClientError:
                    continue
            total_page = int(result.get("totalPage", page))
            if page >= total_page:
                return None
            page += 1

    def _hotspot_client_path(self, site_id: str, path_mac: str, action: str) -> str:
        """Build a hotspot client action path.

        Args:
            site_id: Discovered OpenAPI site ID.
            path_mac: Uppercase dash-separated MAC address.
            action: Hotspot client action (``auth`` or ``unauth``).

        Returns:
            OpenAPI path string.
        """
        return (
            f"/openapi/v1/{self.client.controller_id}/sites/"
            f"{site_id}/hotspot/clients/{path_mac}/{action}"
        )

    @staticmethod
    def _remaining_seconds(record: dict[str, Any]) -> int:
        """Map an OpenAPI status record to best-effort remaining seconds.

        Args:
            record: Authed-record response item.

        Returns:
            Non-negative remaining seconds or zero when absent/expired.
        """
        end = record.get("end")
        if not isinstance(end, int) or end <= 0:
            return 0
        return max(end - int(datetime.now(timezone.utc).timestamp()), 0)
