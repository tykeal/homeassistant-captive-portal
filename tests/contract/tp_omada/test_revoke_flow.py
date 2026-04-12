# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract test for TP-Omada revoke flow (fixture-driven)."""

from __future__ import annotations

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
async def test_omada_revoke_request_structure() -> None:
    """Revoke request must re-auth with time=1, authType=4."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="TestSite")

    captured_payloads: list[dict[str, Any]] = []
    captured_endpoints: list[str] = []

    async def mock_post(endpoint: str, payload: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        """Capture and validate payload."""
        captured_endpoints.append(endpoint)
        captured_payloads.append(payload)
        return {"errorCode": 0, "result": {}}

    client.post_with_retry = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

    await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload["clientMac"] == "AA:BB:CC:DD:EE:FF"
    assert payload["site"] == "TestSite"
    assert payload["time"] == 1
    assert payload["authType"] == 4

    # Verify correct API endpoint path (re-auth, not deauth)
    assert captured_endpoints[0] == "/test-ctrl/api/v2/hotspot/extPortal/auth"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_revoke_includes_gateway_params() -> None:
    """Revoke with gateway params includes them in the payload."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="TestSite")

    captured_payloads: list[dict[str, Any]] = []

    async def mock_post(endpoint: str, payload: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        """Capture payload."""
        captured_payloads.append(payload)
        return {"errorCode": 0, "result": {}}

    client.post_with_retry = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

    await adapter.revoke(
        mac="AA:BB:CC:DD:EE:FF",
        gateway_mac="00:11:22:33:44:55",
        vid="100",
    )

    payload = captured_payloads[0]
    assert payload["gatewayMac"] == "00:11:22:33:44:55"
    assert payload["vid"] == "100"
    assert payload["time"] == 1


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_revoke_response_success() -> None:
    """Successful revoke returns success=True and mac."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value={"errorCode": 0, "result": {}}
    )

    result = await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")
    assert result["success"] is True
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_revoke_response_not_found() -> None:
    """Revoke on non-existent grant (404) treated as success (idempotent)."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    # 404 should be caught and treated as success
    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        side_effect=OmadaClientError("Not found", status_code=404)
    )

    result = await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")
    assert result["success"] is True
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result.get("note") == "Already revoked"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_revoke_succeeds_via_post_with_retry() -> None:
    """Revoke routes through post_with_retry for built-in retry support."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    # Simulate successful revoke via retry-capable path
    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value={"errorCode": 0, "result": {}}
    )

    result = await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")
    assert result["success"] is True


@pytest.mark.contract
@pytest.mark.asyncio
async def test_omada_revoke_idempotent() -> None:
    """Repeated revoke calls should be idempotent (no error on already revoked)."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    client.post_with_retry = AsyncMock(  # type: ignore[method-assign]
        return_value={"errorCode": 0, "result": {}}
    )

    result1 = await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")
    result2 = await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")

    assert result1["success"] is True
    assert result2["success"] is True
    assert client.post_with_retry.call_count == 2
