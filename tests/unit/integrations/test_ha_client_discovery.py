# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for HAClient.get_all_states discovery method (T007)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_get_all_states_success_returns_entity_list() -> None:
    """get_all_states returns the full entity list from HA API."""
    from captive_portal.integrations.ha_client import HAClient

    entities = [
        {"entity_id": "calendar.rental_control_unit1", "state": "on"},
        {"entity_id": "sensor.temperature", "state": "22.5"},
        {"entity_id": "calendar.rental_control_unit2", "state": "off"},
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = entities
    mock_response.raise_for_status = MagicMock()

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        result = await client.get_all_states()

    assert result == entities
    assert len(result) == 3
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_get_all_states_calls_correct_url() -> None:
    """get_all_states calls GET {base_url}/states."""
    from captive_portal.integrations.ha_client import HAClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        await client.get_all_states()

    call_args = mock_get.call_args
    assert call_args[0][0] == "http://supervisor/core/api/states"


@pytest.mark.asyncio
async def test_get_all_states_http_401_raises_auth_error() -> None:
    """HTTP 401 response raises HAAuthenticationError."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_errors import HAAuthenticationError

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized", request=MagicMock(), response=mock_response
    )

    client = HAClient(base_url="http://supervisor/core/api", token="bad_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        with pytest.raises(HAAuthenticationError) as exc_info:
            await client.get_all_states()

    assert exc_info.value.user_message
    assert "bad_token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_all_states_http_500_raises_server_error() -> None:
    """HTTP 5xx response raises HAServerError."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_errors import HAServerError

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error", request=MagicMock(), response=mock_response
    )

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        with pytest.raises(HAServerError) as exc_info:
            await client.get_all_states()

    assert exc_info.value.user_message


@pytest.mark.asyncio
async def test_get_all_states_http_502_raises_server_error() -> None:
    """HTTP 502 (another 5xx) also raises HAServerError."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_errors import HAServerError

    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "502 Bad Gateway", request=MagicMock(), response=mock_response
    )

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        with pytest.raises(HAServerError):
            await client.get_all_states()


@pytest.mark.asyncio
async def test_get_all_states_connect_error_raises_connection_error() -> None:
    """httpx.ConnectError raises HAConnectionError."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_errors import HAConnectionError

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch.object(client.client, "get", mock_get):
        with pytest.raises(HAConnectionError) as exc_info:
            await client.get_all_states()

    assert exc_info.value.user_message
    assert "Connection refused" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_all_states_timeout_raises_timeout_error() -> None:
    """httpx.TimeoutException raises HATimeoutError."""
    from captive_portal.integrations.ha_client import HAClient
    from captive_portal.integrations.ha_errors import HATimeoutError

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(side_effect=httpx.TimeoutException("Read timed out"))

    with patch.object(client.client, "get", mock_get):
        with pytest.raises(HATimeoutError) as exc_info:
            await client.get_all_states()

    assert exc_info.value.user_message


@pytest.mark.asyncio
async def test_get_all_states_uses_configurable_timeout() -> None:
    """get_all_states passes timeout parameter to the HTTP call."""
    from captive_portal.integrations.ha_client import HAClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        await client.get_all_states(timeout=5.0)

    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs.get("timeout") == 5.0


@pytest.mark.asyncio
async def test_get_all_states_default_timeout_is_10s() -> None:
    """get_all_states default timeout is 10 seconds."""
    from captive_portal.integrations.ha_client import HAClient

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    client = HAClient(base_url="http://supervisor/core/api", token="test_token")
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(client.client, "get", mock_get):
        await client.get_all_states()

    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs.get("timeout") == 10.0
