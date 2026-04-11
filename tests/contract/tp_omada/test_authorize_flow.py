# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract test for TP-Omada authorize flow (fixture-driven)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import (
    OmadaClient,
    OmadaClientError,
)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_authorize_request_structure() -> None:
    """Authorize request must include device MAC, expires_at, site_id."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
        verify_ssl=False,
    )
    adapter = OmadaAdapter(client=client, site_id="TestSite")

    # Mock the client's post_with_retry to capture payload
    captured_payloads: list[dict[str, Any]] = []
    captured_endpoints: list[str] = []

    async def mock_post(endpoint: str, payload: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        """Capture and validate payload."""
        captured_endpoints.append(endpoint)
        captured_payloads.append(payload)
        return {"errorCode": 0, "result": {"clientId": "test-id", "authorized": True}}

    client.post_with_retry = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

    expires = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    await adapter.authorize(mac="AA:BB:CC:DD:EE:FF", expires_at=expires)

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload["clientMac"] == "AA:BB:CC:DD:EE:FF"
    assert payload["site"] == "TestSite"
    assert "time" in payload
    assert payload["authType"] == 4
    assert "upKbps" in payload
    assert "downKbps" in payload

    # Verify correct API endpoint path
    assert captured_endpoints[0] == "/test-ctrl/api/v2/hotspot/extPortal/auth"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_authorize_response_success() -> None:
    """Successful authorize returns grant_id and status=active."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value={"errorCode": 0, "result": {"clientId": "grant-xyz", "authorized": True}}
    )

    result = await adapter.authorize(
        mac="AA:BB:CC:DD:EE:FF",
        expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )

    assert result["grant_id"] == "grant-xyz"
    assert result["status"] == "active"
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_authorize_response_error() -> None:
    """Failed authorize with 4xx raises OmadaClientError."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        side_effect=OmadaClientError("Client error 400: Invalid MAC", status_code=400)
    )

    with pytest.raises(OmadaClientError):
        await adapter.authorize(
            mac="INVALID",
            expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_authorize_succeeds_via_post_with_retry() -> None:
    """Authorize routes through post_with_retry for built-in retry support."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    # Adapter delegates to post_with_retry which handles retries
    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value={"errorCode": 0, "result": {"clientId": "retry-ok", "authorized": True}}
    )

    result = await adapter.authorize(
        mac="AA:BB:CC:DD:EE:FF",
        expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    assert result["grant_id"] == "retry-ok"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_authorize_idempotent() -> None:
    """Repeated authorize calls with same MAC should be idempotent."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value={"errorCode": 0, "result": {"clientId": "grant-1", "authorized": True}}
    )

    expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
    result1 = await adapter.authorize(mac="AA:BB:CC:DD:EE:FF", expires_at=expires)
    result2 = await adapter.authorize(mac="AA:BB:CC:DD:EE:FF", expires_at=expires)

    assert result1["grant_id"] == result2["grant_id"]
    assert client.post_with_retry.call_count == 2
