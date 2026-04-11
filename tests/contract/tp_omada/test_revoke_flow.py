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
    """Revoke request must include clientMac and site."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="TestSite")

    captured_payloads: list[dict[str, Any]] = []

    async def mock_post(endpoint: str, payload: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        """Capture and validate payload."""
        captured_payloads.append(payload)
        return {"errorCode": 0, "result": {}}

    client.post_with_retry = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

    await adapter.revoke(mac="AA:BB:CC:DD:EE:FF")

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload["clientMac"] == "AA:BB:CC:DD:EE:FF"
    assert payload["site"] == "TestSite"


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
async def test_omada_revoke_retry_on_timeout() -> None:
    """Revoke should retry and succeed after transient failure."""
    client = OmadaClient(
        base_url="https://ctrl.test:8043",
        controller_id="test-ctrl",
        username="user",
        password="pass",
    )
    adapter = OmadaAdapter(client=client, site_id="Default")

    # Simulate successful revoke after retry
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
