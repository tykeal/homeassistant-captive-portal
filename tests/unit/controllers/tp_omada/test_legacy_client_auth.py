# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for legacy TP-Omada client authentication response handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from captive_portal.controllers.tp_omada.legacy_client import (
    OmadaAuthenticationError,
    OmadaLegacyClient,
)


@pytest.mark.asyncio
async def test_authenticate_malformed_result_raises_auth_error() -> None:
    """Malformed login result raises OmadaAuthenticationError."""
    client = OmadaLegacyClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="operator",
        password="secret",
    )
    response = MagicMock()
    response.json.return_value = {"errorCode": 0, "result": None}
    response.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=response)
    client._client = http_client

    with pytest.raises(OmadaAuthenticationError, match="CSRF token not found"):
        await client._authenticate()


@pytest.mark.asyncio
async def test_authenticate_non_string_token_raises_auth_error() -> None:
    """Non-string login tokens are rejected before header construction."""
    client = OmadaLegacyClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="operator",
        password="secret",
    )
    response = MagicMock()
    response.json.return_value = {"errorCode": 0, "result": {"token": ["not", "string"]}}
    response.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=response)
    client._client = http_client

    with pytest.raises(OmadaAuthenticationError, match="CSRF token not found"):
        await client._authenticate()
