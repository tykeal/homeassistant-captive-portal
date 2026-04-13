# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract test for HA Rental Control entity discovery."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from captive_portal.integrations.ha_client import HAClient
from captive_portal.integrations.ha_errors import HAConnectionError


@pytest_asyncio.fixture
async def ha_client() -> AsyncGenerator[HAClient, None]:
    """Create HAClient with mocked transport."""
    client = HAClient(base_url="http://ha-test.local/api", token="test-token")
    yield client
    await client.close()


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ha_entity_discovery_request(ha_client: HAClient) -> None:
    """Entity discovery request to HA REST API."""
    assert "Authorization" in ha_client.client.headers
    assert ha_client.client.headers["Authorization"] == "Bearer test-token"


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ha_entity_discovery_response_structure(
    ha_client: HAClient,
) -> None:
    """HA entity list response contains entity_id, state, attributes."""
    mock_response = httpx.Response(
        200,
        json=[
            {
                "entity_id": "sensor.rental_control_test_event_0",
                "state": "on",
                "attributes": {
                    "slot_code": "ABC123",
                    "slot_name": "Guest Room",
                    "start": "2025-01-01T12:00:00",
                    "end": "2025-01-03T11:00:00",
                },
            }
        ],
        request=httpx.Request("GET", "http://ha-test.local/api/states"),
    )
    ha_client.client = AsyncMock()
    ha_client.client.get = AsyncMock(return_value=mock_response)

    states = await ha_client.get_all_states()
    assert len(states) == 1
    entity = states[0]
    assert "entity_id" in entity
    assert "state" in entity
    assert "attributes" in entity


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ha_entity_event_attributes_validation(
    ha_client: HAClient,
) -> None:
    """Event sensor attributes must include start, end, slot_name, slot_code."""
    mock_response = httpx.Response(
        200,
        json=[
            {
                "entity_id": "sensor.rental_control_abc_event_0",
                "state": "on",
                "attributes": {
                    "start": "2025-01-01T12:00:00",
                    "end": "2025-01-03T11:00:00",
                    "slot_name": "Guest Room",
                    "slot_code": "ABC123",
                },
            }
        ],
        request=httpx.Request("GET", "http://ha-test.local/api/states"),
    )
    ha_client.client = AsyncMock()
    ha_client.client.get = AsyncMock(return_value=mock_response)

    states = await ha_client.get_all_states()
    attrs = states[0]["attributes"]
    assert "start" in attrs
    assert "end" in attrs
    assert "slot_name" in attrs
    assert "slot_code" in attrs


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ha_entity_discovery_unavailable(ha_client: HAClient) -> None:
    """HA API unavailable returns timeout or connection error."""
    ha_client.client = AsyncMock()
    ha_client.client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    with pytest.raises(HAConnectionError):
        await ha_client.get_all_states()


@pytest.mark.contract
@pytest.mark.asyncio
async def test_ha_entity_discovery_empty_result(ha_client: HAClient) -> None:
    """No matching rental_control entities returns empty list."""
    mock_response = httpx.Response(
        200,
        json=[],
        request=httpx.Request("GET", "http://ha-test.local/api/states"),
    )
    ha_client.client = AsyncMock()
    ha_client.client.get = AsyncMock(return_value=mock_response)

    states = await ha_client.get_all_states()
    assert states == []
