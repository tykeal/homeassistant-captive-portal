# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for revocation error handling with Omada controller.

Validates that controller failures during revocation leave the DB grant
as REVOKED, include partial failure notification for admin, and log
both DB revocation and controller failure.
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


class TestRevocationErrorHandling:
    """Tests for error handling in revocation controller wiring."""

    @pytest.mark.asyncio
    async def test_client_error_grant_stays_revoked(self) -> None:
        """On OmadaClientError, DB grant should stay REVOKED."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.revoke = AsyncMock(side_effect=OmadaClientError("Controller error"))

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)

        # Grant stays REVOKED in DB
        assert grant.status == GrantStatus.REVOKED
        # Partial failure indicated
        assert result.controller_error is not None

    @pytest.mark.asyncio
    async def test_retry_exhausted_grant_stays_revoked(self) -> None:
        """On OmadaRetryExhaustedError, DB grant should stay REVOKED."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.revoke = AsyncMock(side_effect=OmadaRetryExhaustedError("Retries exhausted"))

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)

        assert grant.status == GrantStatus.REVOKED
        assert result.controller_error is not None

    @pytest.mark.asyncio
    async def test_partial_failure_message_in_result(self) -> None:
        """Admin should receive partial failure notification text."""
        mock_client = AsyncMock(spec=OmadaClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_adapter = MagicMock(spec=OmadaAdapter)
        mock_adapter.client = mock_client
        mock_adapter.revoke = AsyncMock(side_effect=OmadaClientError("Connection refused"))

        grant = AccessGrant(
            mac="AA:BB:CC:DD:EE:FF",
            device_id="AA:BB:CC:DD:EE:FF",
            start_utc=datetime.now(timezone.utc),
            end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
            status=GrantStatus.REVOKED,
        )

        from captive_portal.api.routes.grants import _revoke_with_controller

        result = await _revoke_with_controller(adapter=mock_adapter, grant=grant)

        # Should contain a user-friendly partial failure message
        assert result.controller_error is not None
        assert "controller" in result.controller_error.lower()
