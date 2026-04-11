# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest authorization controller wiring.

Validates that the guest authorization flow correctly calls the Omada
controller to authorize devices, and degrades gracefully when unconfigured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import OmadaClient
from captive_portal.models.access_grant import AccessGrant, GrantStatus


class TestGuestAuthorizationControllerWiring:
    """Tests for Omada controller wiring in guest authorization."""

    @pytest.mark.asyncio
    async def test_adapter_authorize_called_when_configured(self) -> None:
        """When adapter is configured, adapter.authorize() should be called."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.authorize = AsyncMock(
            return_value={
                "grant_id": "ctrl-grant-1",
                "status": "active",
                "mac": "AA:BB:CC:DD:EE:FF",
            }
        )

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.PENDING,
        )

        # Simulate the wiring logic
        from captive_portal.api.routes.guest_portal import _authorize_with_controller

        result, error_detail = await _authorize_with_controller(
            adapter=mock_adapter, grant=grant, mac_address="AA:BB:CC:DD:EE:FF"
        )

        mock_client.__aenter__.assert_called_once()
        mock_adapter.authorize.assert_awaited_once()
        assert result.status == GrantStatus.ACTIVE
        assert result.controller_grant_id == "ctrl-grant-1"
        assert error_detail is None

    @pytest.mark.asyncio
    async def test_grant_active_without_controller(self) -> None:
        """When adapter is None, grant should transition PENDING→ACTIVE directly."""
        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.PENDING,
        )

        from captive_portal.api.routes.guest_portal import _authorize_with_controller

        result, error_detail = await _authorize_with_controller(
            adapter=None, grant=grant, mac_address="AA:BB:CC:DD:EE:FF"
        )

        assert result.status == GrantStatus.ACTIVE
        assert result.controller_grant_id is None
        assert error_detail is None

    @pytest.mark.asyncio
    async def test_per_operation_context_manager_used(self) -> None:
        """async with adapter.client: should be used for each operation."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.authorize = AsyncMock(
            return_value={
                "grant_id": "ctrl-grant-1",
                "status": "active",
                "mac": "AA:BB:CC:DD:EE:FF",
            }
        )

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.PENDING,
        )

        from captive_portal.api.routes.guest_portal import _authorize_with_controller

        _grant, _error_detail = await _authorize_with_controller(
            adapter=mock_adapter, grant=grant, mac_address="AA:BB:CC:DD:EE:FF"
        )

        # Verify async context manager was used
        mock_client.__aenter__.assert_called_once()
        mock_client.__aexit__.assert_called_once()
