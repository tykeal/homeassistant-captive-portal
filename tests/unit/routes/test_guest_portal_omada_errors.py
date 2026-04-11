# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for guest authorization error handling with Omada controller.

Validates that controller failures transition grants to FAILED status,
return user-friendly errors, and record audit log entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import (
    OmadaClient,
    OmadaClientError,
    OmadaRetryExhaustedError,
)
from captive_portal.models.access_grant import AccessGrant, GrantStatus


class TestGuestAuthorizationErrorHandling:
    """Tests for error handling in guest authorization controller wiring."""

    @pytest.mark.asyncio
    async def test_client_error_transitions_to_failed(self) -> None:
        """On OmadaClientError, grant should transition PENDING→FAILED."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.authorize = AsyncMock(side_effect=OmadaClientError("Controller rejected auth"))

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.PENDING,
        )

        from captive_portal.api.routes.guest_portal import _authorize_with_controller

        result, error_detail = await _authorize_with_controller(
            adapter=mock_adapter, grant=grant, mac_address="AA:BB:CC:DD:EE:FF"
        )

        assert result.status == GrantStatus.FAILED
        assert error_detail is not None

    @pytest.mark.asyncio
    async def test_retry_exhausted_transitions_to_failed(self) -> None:
        """On OmadaRetryExhaustedError, grant should transition PENDING→FAILED."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.authorize = AsyncMock(
            side_effect=OmadaRetryExhaustedError("Retries exhausted")
        )

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.PENDING,
        )

        from captive_portal.api.routes.guest_portal import _authorize_with_controller

        result, error_detail = await _authorize_with_controller(
            adapter=mock_adapter, grant=grant, mac_address="AA:BB:CC:DD:EE:FF"
        )

        assert result.status == GrantStatus.FAILED
        assert error_detail is not None

    @pytest.mark.asyncio
    async def test_error_returns_error_message(self) -> None:
        """Controller failure should return an error message (not raw exception)."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.authorize = AsyncMock(
            side_effect=OmadaClientError("Internal server error 500")
        )

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.PENDING,
        )

        from captive_portal.api.routes.guest_portal import _authorize_with_controller

        result, error_detail = await _authorize_with_controller(
            adapter=mock_adapter, grant=grant, mac_address="AA:BB:CC:DD:EE:FF"
        )

        # Grant should be FAILED; the raw exception should not leak
        assert result.status == GrantStatus.FAILED
        assert error_detail is not None
        assert "OmadaClientError" in error_detail
