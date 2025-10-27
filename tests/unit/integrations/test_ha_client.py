# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for HA client REST API wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_ha_client_get_entity_state_success() -> None:
    """Test successful entity state retrieval from HA."""
    from captive_portal.integrations.ha_client import HAClient

    mock_response_data = {
        "entity_id": "calendar.rental_control_test",
        "state": "on",
        "attributes": {
            "message": "Test Booking",
            "start_time": "2025-10-26T10:00:00+00:00",
            "end_time": "2025-10-26T15:00:00+00:00",
        },
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        client = HAClient(base_url="http://supervisor/core/api", token="test_token")
        result = await client.get_entity_state("calendar.rental_control_test")

        assert result == mock_response_data
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_ha_client_get_entity_state_not_found() -> None:
    """Test entity not found returns None."""
    from captive_portal.integrations.ha_client import HAClient

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        client = HAClient(base_url="http://supervisor/core/api", token="test_token")
        result = await client.get_entity_state("calendar.nonexistent")

        assert result is None


@pytest.mark.asyncio
async def test_ha_client_authentication_header() -> None:
    """Test client sends correct authentication header."""
    from captive_portal.integrations.ha_client import HAClient

    client = HAClient(base_url="http://supervisor/core/api", token="secret_token")

    # Verify auth header is set in client headers
    assert client.client.headers["Authorization"] == "Bearer secret_token"


@pytest.mark.asyncio
async def test_ha_client_handles_http_errors() -> None:
    """Test client handles HTTP errors gracefully."""
    import httpx
    from captive_portal.integrations.ha_client import HAClient

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=mock_response
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        client = HAClient(base_url="http://supervisor/core/api", token="test_token")

        with pytest.raises(Exception, match="HA API request failed"):
            await client.get_entity_state("sensor.test")
