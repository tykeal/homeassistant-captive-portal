# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada controller ID auto-discovery.

Validates ``discover_controller_id()`` against success, error-code,
missing-field, HTTP-error, connection-error, and invalid-JSON scenarios
by patching ``httpx.AsyncClient`` with async mocks.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from captive_portal.controllers.tp_omada.base_client import (
    OmadaClientError,
    discover_controller_id,
)


def _make_response(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
) -> httpx.Response:
    """Build a canned ``httpx.Response``.

    Args:
        status_code: HTTP status code.
        body: JSON body dict.

    Returns:
        An httpx.Response with the given status and body.
    """
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(body or {}).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://controller:443/api/info"),
    )


@pytest.mark.parametrize("base_url", ["http://controller:8088", "https://controller:443"])
@pytest.mark.asyncio
async def test_discover_success(base_url: str) -> None:
    """Successful discovery accepts HTTP and HTTPS controller URLs."""
    resp = _make_response(
        body={
            "errorCode": 0,
            "result": {
                "omadacId": "abc123def456",
                "controllerVer": "6.0.0.39",
            },
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await discover_controller_id(base_url)

    assert result == "abc123def456"
    mock_client.get.assert_awaited_once_with(f"{base_url}/api/info")


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///etc/passwd",
        "ftp://controller.example.test",
        "",
        "https:///api/info",
        "http://[::1",
        "https://controller.example.test:bad",
        "https://controller.example.test:99999",
        "https://controller example.test",
        "https://controller.example.test/api path",
    ],
)
@pytest.mark.asyncio
async def test_discover_rejects_invalid_controller_url_without_request(
    base_url: str,
) -> None:
    """Invalid controller URLs raise before any HTTP client is opened."""
    with patch("httpx.AsyncClient") as async_client:
        with pytest.raises(OmadaClientError, match="Invalid Omada controller URL"):
            await discover_controller_id(base_url)

    async_client.assert_not_called()


@pytest.mark.asyncio
async def test_discover_error_code_nonzero() -> None:
    """Non-zero errorCode raises OmadaClientError."""
    resp = _make_response(
        body={
            "errorCode": -1,
            "msg": "Internal error",
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OmadaClientError, match="Controller info request failed"):
            await discover_controller_id("https://controller:443")


@pytest.mark.asyncio
async def test_discover_missing_omadac_id() -> None:
    """Missing omadacId in response raises OmadaClientError."""
    resp = _make_response(
        body={
            "errorCode": 0,
            "result": {"controllerVer": "6.0.0.39"},
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OmadaClientError, match="omadacId not found"):
            await discover_controller_id("https://controller:443")


@pytest.mark.asyncio
async def test_discover_malformed_result_raises_client_error() -> None:
    """Malformed result payload raises OmadaClientError instead of AttributeError."""
    resp = _make_response(
        body={
            "errorCode": 0,
            "result": None,
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OmadaClientError, match="omadacId not found"):
            await discover_controller_id("https://controller:443")


@pytest.mark.asyncio
async def test_discover_http_error() -> None:
    """HTTP error status raises OmadaClientError."""
    resp = _make_response(status_code=500, body={"error": "fail"})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OmadaClientError, match="HTTP 500"):
            await discover_controller_id("https://controller:443")


@pytest.mark.asyncio
async def test_discover_connection_error() -> None:
    """Connection error raises OmadaClientError."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OmadaClientError, match="Connection error"):
            await discover_controller_id("https://controller:443")


@pytest.mark.asyncio
async def test_discover_invalid_json() -> None:
    """Non-JSON response raises OmadaClientError."""
    resp = httpx.Response(
        status_code=200,
        content=b"<html>Not JSON</html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", "https://controller:443/api/info"),
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OmadaClientError, match="Invalid JSON"):
            await discover_controller_id("https://controller:443")
