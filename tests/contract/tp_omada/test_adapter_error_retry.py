# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for TP-Omada adapter error handling and retry logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from captive_portal.controllers.tp_omada.base_client import (
    OmadaClient,
    OmadaClientError,
    OmadaRetryExhaustedError,
)


class TestOmadaAdapterRetry:
    """Test TP-Omada adapter exponential backoff and retry logic."""

    @pytest.mark.asyncio
    async def test_authorize_retries_on_connection_error(self) -> None:
        """Adapter should retry authorize on connection errors with backoff."""
        client = OmadaClient(
            base_url="https://ctrl.test:8043",
            controller_id="test-ctrl",
            username="user",
            password="pass",
            verify_ssl=False,
        )

        # Create mock httpx client
        mock_http = AsyncMock()
        call_count = 0

        async def mock_post(*args: object, **kwargs: object) -> MagicMock:
            """Simulate connection errors then success."""
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.ConnectError("Connection refused")
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"errorCode": 0, "result": {"clientId": "test-mac"}}
            response.content = b'{"errorCode": 0}'
            response.raise_for_status = MagicMock()
            return response

        mock_http.post = AsyncMock(side_effect=mock_post)
        client._client = mock_http
        client._csrf_token = "test-token"

        with patch(
            "captive_portal.controllers.tp_omada.base_client.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await client.post_with_retry(
                "/extportal/auth", {"clientMac": "AA:BB:CC:DD:EE:FF"}
            )

        assert result["errorCode"] == 0
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_authorize_fails_after_max_retries(self) -> None:
        """Adapter should raise OmadaRetryExhaustedError after max retries."""
        client = OmadaClient(
            base_url="https://ctrl.test:8043",
            controller_id="test-ctrl",
            username="user",
            password="pass",
        )

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        client._client = mock_http
        client._csrf_token = "test-token"

        with patch(
            "captive_portal.controllers.tp_omada.base_client.asyncio.sleep", new_callable=AsyncMock
        ):
            with pytest.raises(OmadaRetryExhaustedError):
                await client.post_with_retry("/extportal/auth", {"clientMac": "AA:BB:CC:DD:EE:FF"})

    @pytest.mark.asyncio
    async def test_authorize_does_not_retry_on_4xx_errors(self) -> None:
        """Adapter should NOT retry on 4xx client errors (permanent failures)."""
        client = OmadaClient(
            base_url="https://ctrl.test:8043",
            controller_id="test-ctrl",
            username="user",
            password="pass",
        )

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"errorCode": -1, "msg": "Invalid parameters"}'
        mock_response.json.return_value = {"errorCode": -1, "msg": "Invalid parameters"}
        mock_response.text = "Invalid parameters"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http
        client._csrf_token = "test-token"

        with pytest.raises(OmadaClientError):
            await client.post_with_retry("/extportal/auth", {"clientMac": "AA:BB:CC:DD:EE:FF"})

        # Should only be called once (no retries for 4xx)
        assert mock_http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_authorize_retries_on_5xx_errors(self) -> None:
        """Adapter should retry on 5xx server errors (transient failures)."""
        client = OmadaClient(
            base_url="https://ctrl.test:8043",
            controller_id="test-ctrl",
            username="user",
            password="pass",
        )

        call_count = 0

        async def mock_post(*args: object, **kwargs: object) -> MagicMock:
            """Simulate 503 then success."""
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if call_count == 1:
                response.status_code = 503
                response.text = "Service Unavailable"
                response.content = b"Service Unavailable"
            else:
                response.status_code = 200
                response.json.return_value = {"errorCode": 0, "result": {"clientId": "test-mac"}}
                response.content = b'{"errorCode": 0}'
                response.raise_for_status = MagicMock()
            return response

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=mock_post)
        client._client = mock_http
        client._csrf_token = "test-token"

        with patch(
            "captive_portal.controllers.tp_omada.base_client.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await client.post_with_retry("/extportal/auth", {"clientMac": "test"})

        assert result["errorCode"] == 0
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_revoke_retries_on_timeout(self) -> None:
        """Revoke should retry on timeout errors."""
        client = OmadaClient(
            base_url="https://ctrl.test:8043",
            controller_id="test-ctrl",
            username="user",
            password="pass",
        )

        call_count = 0

        async def mock_post(*args: object, **kwargs: object) -> MagicMock:
            """Simulate timeout then success."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Request timeout")
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"errorCode": 0, "result": {}}
            response.content = b'{"errorCode": 0}'
            response.raise_for_status = MagicMock()
            return response

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=mock_post)
        client._client = mock_http
        client._csrf_token = "test-token"

        with patch(
            "captive_portal.controllers.tp_omada.base_client.asyncio.sleep", new_callable=AsyncMock
        ):
            result = await client.post_with_retry("/extportal/revoke", {"clientMac": "test"})

        assert result["errorCode"] == 0
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self) -> None:
        """Adapter backoff should follow exponential pattern (1s, 2s, 4s)."""
        client = OmadaClient(
            base_url="https://ctrl.test:8043",
            controller_id="test-ctrl",
            username="user",
            password="pass",
        )

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        client._client = mock_http
        client._csrf_token = "test-token"

        sleep_delays: list[float] = []

        async def mock_sleep(delay: float) -> None:
            """Capture sleep delays."""
            sleep_delays.append(delay)

        with patch(
            "captive_portal.controllers.tp_omada.base_client.asyncio.sleep", side_effect=mock_sleep
        ):
            with pytest.raises(OmadaRetryExhaustedError):
                await client.post_with_retry(
                    "/extportal/auth",
                    {"clientMac": "test"},
                    max_retries=4,
                    backoff_ms=[1000, 2000, 4000, 8000],
                )

        # Verify backoff delays: 1s, 2s, 4s (3 retries between 4 attempts)
        assert len(sleep_delays) == 3
        assert sleep_delays[0] == pytest.approx(1.0)
        assert sleep_delays[1] == pytest.approx(2.0)
        assert sleep_delays[2] == pytest.approx(4.0)
