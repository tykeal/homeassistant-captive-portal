# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Focused error-path tests for Home Assistant communications."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_discovery_service import (
    HADiscoveryService,
    _is_rental_control_calendar,
)
from captive_portal.integrations.ha_errors import (
    HAAuthenticationError,
    HAConnectionError,
    HAServerError,
    HATimeoutError,
)


def _response(status_code: int = 200) -> MagicMock:
    """Build a minimal response mock for HA client tests."""
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_get_all_states_invalid_json_raises_server_error() -> None:
    """Malformed HA state JSON is normalized to a server error."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    response = _response()
    response.json.side_effect = ValueError("bad json")

    with patch.object(client.client, "get", AsyncMock(return_value=response)):
        with pytest.raises(HAServerError) as exc_info:
            await client.get_all_states()

    assert "invalid response" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_get_all_states_unexpected_http_status_raises_server_error() -> None:
    """Non-special HTTP status failures are wrapped as HA server errors."""
    request = httpx.Request("GET", "http://supervisor/core/api/states")
    response = _response(418)
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "teapot",
        request=request,
        response=httpx.Response(418, request=request),
    )
    client = HAClient(base_url="http://supervisor/core/api", token="token")

    with patch.object(client.client, "get", AsyncMock(return_value=response)):
        with pytest.raises(HAServerError) as exc_info:
            await client.get_all_states()

    assert "unexpected error" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_get_all_states_protocol_error_raises_connection_error() -> None:
    """Non-timeout request errors are normalized to connection errors."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")

    with patch.object(
        client.client,
        "get",
        AsyncMock(side_effect=httpx.ProtocolError("bad protocol")),
    ):
        with pytest.raises(HAConnectionError) as exc_info:
            await client.get_all_states()

    assert exc_info.value.detail == "bad protocol"


@pytest.mark.asyncio
async def test_get_entity_registry_success_returns_entries() -> None:
    """Entity-registry success returns decoded entries unchanged."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    entries = [{"entity_id": "calendar.rental_control_guest", "platform": "rental_control"}]
    response = _response()
    response.json.return_value = entries

    with patch.object(client.client, "get", AsyncMock(return_value=response)):
        assert await client.get_entity_registry() == entries


@pytest.mark.asyncio
async def test_get_entity_registry_auth_and_server_errors_reraise() -> None:
    """Entity-registry 401 and 5xx responses preserve typed errors."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    auth_response = _response(401)
    server_response = _response(503)

    with patch.object(client.client, "get", AsyncMock(return_value=auth_response)):
        with pytest.raises(HAAuthenticationError) as auth_exc:
            await client.get_entity_registry()
    with patch.object(client.client, "get", AsyncMock(return_value=server_response)):
        with pytest.raises(HAServerError) as server_exc:
            await client.get_entity_registry()

    assert auth_exc.value.user_message == "Authentication with Home Assistant failed"
    assert "server error" in server_exc.value.user_message


@pytest.mark.asyncio
async def test_get_entity_registry_invalid_json_raises_server_error() -> None:
    """Malformed registry JSON is reported as an invalid HA response."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    response = _response()
    response.json.side_effect = TypeError("not json")

    with patch.object(client.client, "get", AsyncMock(return_value=response)):
        with pytest.raises(HAServerError) as exc_info:
            await client.get_entity_registry()

    assert "invalid response" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_get_entity_registry_transport_errors_are_typed() -> None:
    """Registry connect, timeout, and status failures get typed wrappers."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    request = httpx.Request("GET", "http://supervisor/core/api/config/entity_registry/list")
    status_response = _response(409)
    status_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "conflict",
        request=request,
        response=httpx.Response(409, request=request),
    )

    with patch.object(client.client, "get", AsyncMock(side_effect=httpx.ConnectError("no route"))):
        with pytest.raises(HAConnectionError):
            await client.get_entity_registry()
    with patch.object(
        client.client,
        "get",
        AsyncMock(side_effect=httpx.TimeoutException("slow")),
    ):
        with pytest.raises(HATimeoutError):
            await client.get_entity_registry()
    with patch.object(client.client, "get", AsyncMock(return_value=status_response)):
        with pytest.raises(HAServerError):
            await client.get_entity_registry()


@pytest.mark.asyncio
async def test_get_timezone_invalid_json_and_transport_errors_are_typed() -> None:
    """Timezone invalid JSON, connect, timeout, and status paths are typed."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    bad_json = _response()
    bad_json.json.side_effect = ValueError("bad json")
    request = httpx.Request("GET", "http://supervisor/core/api/config")
    bad_status = _response(409)
    bad_status.raise_for_status.side_effect = httpx.HTTPStatusError(
        "conflict",
        request=request,
        response=httpx.Response(409, request=request),
    )

    with patch.object(client.client, "get", AsyncMock(return_value=bad_json)):
        with pytest.raises(HAServerError):
            await client.get_timezone()
    with patch.object(client.client, "get", AsyncMock(side_effect=httpx.ConnectError("down"))):
        with pytest.raises(HAConnectionError):
            await client.get_timezone()
    with patch.object(
        client.client,
        "get",
        AsyncMock(side_effect=httpx.TimeoutException("slow")),
    ):
        with pytest.raises(HATimeoutError):
            await client.get_timezone()
    with patch.object(client.client, "get", AsyncMock(return_value=bad_status)):
        with pytest.raises(HAServerError):
            await client.get_timezone()


@pytest.mark.asyncio
async def test_ha_client_context_manager_closes_client() -> None:
    """HAClient returns itself and closes when leaving async context."""
    client = HAClient(base_url="http://supervisor/core/api", token="token")
    close_mock = AsyncMock()

    with patch.object(client, "close", close_mock):
        async with client as entered:
            assert entered is client

    close_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_ha_poller_stop_swallows_task_cancellation() -> None:
    """Stopping a poller with a stored task cancels and awaits it cleanly."""
    from captive_portal.integrations.ha_poller import HAPoller

    async def sleep_forever() -> None:
        """Block until the poller cancels the task."""
        await asyncio.sleep(60)

    poller = HAPoller(ha_client=MagicMock(), rental_service=MagicMock())
    poller._task = asyncio.create_task(sleep_forever())

    await poller.stop()

    assert poller._task.cancelled()


def test_rental_control_calendar_detection_uses_friendly_name() -> None:
    """Friendly-name fallback identifies Rental Control calendars."""
    entity = {
        "entity_id": "calendar.guest_suite",
        "attributes": {"friendly_name": "Rental Control Guest Suite"},
    }

    assert _is_rental_control_calendar(entity)


@pytest.mark.asyncio
async def test_discovery_uses_entity_id_when_friendly_name_blank() -> None:
    """Discovery falls back to the entity ID for blank friendly names."""
    ha_client = MagicMock()
    ha_client.get_entity_registry = AsyncMock(
        side_effect=HAConnectionError("Registry unavailable"),
    )
    ha_client.get_all_states = AsyncMock(
        return_value=[
            {
                "entity_id": "calendar.rental_control_guest",
                "state": "on",
                "attributes": {"friendly_name": " "},
            }
        ],
    )
    session = MagicMock()
    session.exec.return_value = []
    service = HADiscoveryService(ha_client=ha_client, session=session)

    result = await service.discover()

    assert result.integrations[0].friendly_name == "calendar.rental_control_guest"
