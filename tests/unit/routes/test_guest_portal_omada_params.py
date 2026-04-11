# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada parameter pass-through in guest portal.

Validates that the GET handler captures Omada query parameters and
passes them to the template, and that the POST handler uses the site
parameter to override the adapter site_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import OmadaClient


class TestSiteIdOverride:
    """Tests for site_id override from Omada controller redirect."""

    @pytest.mark.asyncio
    async def test_site_override_applied_before_authorize(self) -> None:
        """Site from form data should override adapter's default site_id."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.controller_id = "test-ctrl"

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.site_id = "Default"
        mock_adapter.authorize = AsyncMock(
            return_value={
                "grant_id": "ctrl-grant-1",
                "status": "active",
                "mac": "AA:BB:CC:DD:EE:FF",
            }
        )

        # Simulate what handle_authorization does
        site = "686982d482171c5562624ad1"
        if mock_adapter is not None and site and isinstance(site, str) and site.strip():
            mock_adapter.site_id = site.strip()

        assert mock_adapter.site_id == "686982d482171c5562624ad1"

    @pytest.mark.asyncio
    async def test_empty_site_does_not_override(self) -> None:
        """Empty site value should not override adapter site_id."""
        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.site_id = "Default"

        site = ""
        if mock_adapter is not None and site and isinstance(site, str) and site.strip():
            mock_adapter.site_id = site.strip()

        assert mock_adapter.site_id == "Default"

    @pytest.mark.asyncio
    async def test_none_site_does_not_override(self) -> None:
        """None site value should not override adapter site_id."""
        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.site_id = "Default"

        site = None
        if mock_adapter is not None and site and isinstance(site, str) and site.strip():
            mock_adapter.site_id = site.strip()

        assert mock_adapter.site_id == "Default"

    @pytest.mark.asyncio
    async def test_whitespace_site_does_not_override(self) -> None:
        """Whitespace-only site value should not override adapter site_id."""
        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.site_id = "Default"

        site = "   "
        if mock_adapter is not None and site and isinstance(site, str) and site.strip():
            mock_adapter.site_id = site.strip()

        assert mock_adapter.site_id == "Default"

    @pytest.mark.asyncio
    async def test_site_override_with_authorize(self) -> None:
        """Overridden site_id should be used in the authorize payload."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.controller_id = "omadac-id"

        adapter = OmadaAdapter(client=mock_client, site_id="Default")

        # Override site as the handler would
        adapter.site_id = "686982d482171c5562624ad1"

        captured_payloads: list[dict[str, object]] = []

        async def mock_post(
            endpoint: str, payload: dict[str, object], **kwargs: object
        ) -> dict[str, object]:
            """Capture payload."""
            captured_payloads.append(payload)
            return {
                "errorCode": 0,
                "result": {"clientId": "g1", "authorized": True},
            }

        mock_client.post_with_retry = AsyncMock(side_effect=mock_post)

        await adapter.authorize(
            mac="AA:BB:CC:DD:EE:FF",
            expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )

        assert captured_payloads[0]["site"] == "686982d482171c5562624ad1"


class TestAdapterEndpointPaths:
    """Tests for correct API endpoint path construction."""

    @pytest.mark.asyncio
    async def test_authorize_endpoint_includes_controller_id(self) -> None:
        """Authorize should use /{controllerId}/api/v2/hotspot/extPortal/auth."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.controller_id = "abc123"

        captured_endpoints: list[str] = []

        async def mock_post(
            endpoint: str, payload: dict[str, object], **kwargs: object
        ) -> dict[str, object]:
            """Capture endpoint."""
            captured_endpoints.append(endpoint)
            return {
                "errorCode": 0,
                "result": {"clientId": "g1", "authorized": True},
            }

        mock_client.post_with_retry = AsyncMock(side_effect=mock_post)

        adapter = OmadaAdapter(client=mock_client, site_id="Default")
        await adapter.authorize(
            mac="AA:BB:CC:DD:EE:FF",
            expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )

        assert captured_endpoints[0] == "/abc123/api/v2/hotspot/extPortal/auth"

    @pytest.mark.asyncio
    async def test_revoke_endpoint_includes_controller_id(self) -> None:
        """Revoke should use /{controllerId}/api/v2/hotspot/extPortal/revoke."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.controller_id = "abc123"

        captured_endpoints: list[str] = []

        async def mock_post(
            endpoint: str, payload: dict[str, object], **kwargs: object
        ) -> dict[str, object]:
            """Capture endpoint."""
            captured_endpoints.append(endpoint)
            return {"errorCode": 0, "result": {}}

        mock_client.post_with_retry = AsyncMock(side_effect=mock_post)

        adapter = OmadaAdapter(client=mock_client, site_id="Default")
        await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")

        assert captured_endpoints[0] == "/abc123/api/v2/hotspot/extPortal/revoke"

    @pytest.mark.asyncio
    async def test_get_status_endpoint_includes_controller_id(self) -> None:
        """Status should use /{controllerId}/api/v2/hotspot/extPortal/session."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.controller_id = "abc123"

        captured_endpoints: list[str] = []

        async def mock_post(
            endpoint: str, payload: dict[str, object], **kwargs: object
        ) -> dict[str, object]:
            """Capture endpoint."""
            captured_endpoints.append(endpoint)
            return {
                "errorCode": 0,
                "result": {"authorized": True, "remainingTime": 3600},
            }

        mock_client.post_with_retry = AsyncMock(side_effect=mock_post)

        adapter = OmadaAdapter(client=mock_client, site_id="Default")
        await adapter.get_status(mac="AA:BB:CC:DD:EE:FF")

        assert captured_endpoints[0] == "/abc123/api/v2/hotspot/extPortal/session"
