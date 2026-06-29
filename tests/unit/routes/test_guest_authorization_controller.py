# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for extracted guest controller authorization helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus


def test_truncate_strips_empty_and_bounds_values() -> None:
    """Omada metadata truncation preserves current empty and length rules."""
    from captive_portal.api.routes.guest_authorization.controller import truncate

    assert truncate(None, 8) is None
    assert truncate("   ", 8) is None
    assert truncate("  abcdef  ", 3) == "abc"


@pytest.mark.asyncio
async def test_controller_helper_preserves_payload_and_grant_id() -> None:
    """Controller helper forwards metadata and stores returned grant ID."""
    from captive_portal.api.routes.guest_authorization.controller import authorize_with_controller

    adapter = MagicMock(spec=OmadaAdapter)
    adapter.authorize = AsyncMock(return_value={"grant_id": "ctrl-grant"})
    grant = AccessGrant(
        mac="AA:BB:CC:DD:EE:FF",
        device_id="AA:BB:CC:DD:EE:FF",
        start_utc=datetime.now(timezone.utc),
        end_utc=datetime(2026, 12, 31, tzinfo=timezone.utc),
        status=GrantStatus.PENDING,
    )

    result, error_detail = await authorize_with_controller(
        adapter=adapter,
        grant=grant,
        mac_address="AA:BB:CC:DD:EE:FF",
        gateway_mac="11:22:33:44:55:66",
        ap_mac="22:33:44:55:66:77",
        ssid_name="Guest",
        radio_id="1",
        vid="100",
    )

    adapter.authorize.assert_awaited_once_with(
        mac="AA:BB:CC:DD:EE:FF",
        expires_at=grant.end_utc,
        gateway_mac="11:22:33:44:55:66",
        ap_mac="22:33:44:55:66:77",
        ssid_name="Guest",
        radio_id="1",
        vid="100",
    )
    assert result.status == GrantStatus.ACTIVE
    assert result.controller_grant_id == "ctrl-grant"
    assert error_detail is None
