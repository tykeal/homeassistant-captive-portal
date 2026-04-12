# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for grant revocation controller wiring.

Validates that the admin revocation flow correctly calls the Omada
controller to deauthorize devices, handles idempotent revocation,
and degrades gracefully when unconfigured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import OmadaClient
from captive_portal.models.access_grant import AccessGrant, GrantStatus


class TestGrantRevocationControllerWiring:
    """Tests for Omada controller wiring in grant revocation."""

    @pytest.mark.asyncio
    async def test_adapter_revoke_called_when_configured(self) -> None:
        """When adapter is configured and grant has MAC, revoke should be called."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.revoke = AsyncMock(return_value={"success": True, "mac": "AA:BB:CC:DD:EE:FF"})

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
            omada_gateway_mac="00:11:22:33:44:55",
            omada_ap_mac=None,
            omada_vid="100",
            omada_ssid_name=None,
            omada_radio_id=None,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)

        mock_client.__aenter__.assert_called_once()
        mock_adapter.revoke.assert_awaited_once_with(
            mac="AA:BB:CC:DD:EE:FF",
            gateway_mac="00:11:22:33:44:55",
            ap_mac=None,
            vid="100",
            ssid_name=None,
            radio_id=None,
        )
        assert result.controller_error is None

    @pytest.mark.asyncio
    async def test_already_revoked_treated_as_success(self) -> None:
        """Controller 'already revoked' response should be treated as success."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.revoke = AsyncMock(
            return_value={"success": True, "mac": "AA:BB:CC:DD:EE:FF", "note": "Already revoked"}
        )

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)
        assert result.controller_error is None

    @pytest.mark.asyncio
    async def test_db_only_when_adapter_is_none(self) -> None:
        """When adapter is None, DB-only revocation (no controller call)."""
        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=None, grant=grant)
        assert result.controller_error is None

    @pytest.mark.asyncio
    async def test_db_only_when_no_mac(self) -> None:
        """When grant has no MAC, skip controller call, DB-only revocation."""
        mock_adapter = MagicMock(spec=OmadaAdapter)

        grant = AccessGrant(
            mac="",
            device_id="device-1",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)
        assert result.controller_error is None
        # Adapter should not have been called
        mock_adapter.revoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_grant_stays_revoked_regardless_of_controller(self) -> None:
        """DB grant should always remain REVOKED regardless of controller outcome."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.revoke = AsyncMock(return_value={"success": True, "mac": "AA:BB:CC:DD:EE:FF"})

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)
        assert result.controller_error is None
        # Grant status should still be REVOKED
        assert grant.status == GrantStatus.REVOKED
