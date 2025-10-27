# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""TP-Omada HTTP client with authentication and retry logic."""

import asyncio
from typing import Any, Optional
from urllib.parse import urljoin

import httpx


class OmadaClientError(Exception):
    """Base exception for Omada client errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
        """
        super().__init__(message)
        self.status_code = status_code


class OmadaAuthenticationError(OmadaClientError):
    """Raised when authentication with Omada controller fails."""

    pass


class OmadaRetryExhaustedError(OmadaClientError):
    """Raised when retry attempts are exhausted."""

    pass


class OmadaClient:
    """HTTP client for TP-Omada controller API with authentication.

    Attributes:
        base_url: Controller base URL (e.g., https://controller:8043)
        controller_id: Omada controller identifier
        username: Hotspot operator username
        password: Hotspot operator password
        verify_ssl: Whether to verify SSL certificates
    """

    def __init__(
        self,
        base_url: str,
        controller_id: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
        timeout: float = 10.0,
    ) -> None:
        """Initialize Omada client.

        Args:
            base_url: Controller base URL (e.g., https://controller:8043)
            controller_id: Omada controller identifier
            username: Hotspot operator username
            password: Hotspot operator password
            verify_ssl: Whether to verify SSL certificates (default: True)
            timeout: HTTP request timeout in seconds (default: 10.0)
        """
        self.base_url = base_url.rstrip("/")
        self.controller_id = controller_id
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self._client: Optional[httpx.AsyncClient] = None
        self._csrf_token: Optional[str] = None
        self._session_cookie: Optional[str] = None

    async def __aenter__(self) -> "OmadaClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        await self._authenticate()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def _authenticate(self) -> None:
        """Authenticate with Omada controller and obtain CSRF token.

        Raises:
            OmadaAuthenticationError: If authentication fails
        """
        if not self._client:
            raise OmadaClientError("Client not initialized")

        login_url = urljoin(self.base_url, f"/{self.controller_id}/api/v2/hotspot/login")
        payload = {"name": self.username, "password": self.password}

        try:
            response = await self._client.post(login_url, json=payload)
            response.raise_for_status()

            data = response.json()
            if data.get("errorCode") != 0:
                raise OmadaAuthenticationError(
                    f"Omada login failed: {data.get('msg', 'Unknown error')}"
                )

            # Extract CSRF token from response
            self._csrf_token = data.get("result", {}).get("token")
            if not self._csrf_token:
                raise OmadaAuthenticationError("CSRF token not found in login response")

            # Extract session cookie (TPEAP_SESSIONID or TPOMADA_SESSIONID)
            cookies = response.cookies
            self._session_cookie = cookies.get("TPOMADA_SESSIONID") or cookies.get(
                "TPEAP_SESSIONID"
            )
            if not self._session_cookie:
                raise OmadaAuthenticationError("Session cookie not found in response")

        except httpx.HTTPStatusError as e:
            raise OmadaAuthenticationError(f"HTTP {e.response.status_code}: {e}") from e
        except httpx.RequestError as e:
            raise OmadaAuthenticationError(f"Connection error: {e}") from e

    async def post_with_retry(
        self,
        endpoint: str,
        payload: dict[str, Any],
        max_retries: int = 4,
        backoff_ms: list[int] | None = None,
    ) -> dict[str, Any]:
        """POST request with exponential backoff retry logic.

        Args:
            endpoint: API endpoint path (e.g., /extportal/auth)
            payload: JSON request body
            max_retries: Maximum retry attempts (default: 4)
            backoff_ms: Retry backoff delays in milliseconds (default: [1000, 2000, 4000, 8000])

        Returns:
            JSON response dict

        Raises:
            OmadaRetryExhaustedError: If all retries exhausted
            OmadaClientError: On non-retryable errors (4xx)
        """
        if not self._client:
            raise OmadaClientError("Client not initialized")

        if backoff_ms is None:
            backoff_ms = [1000, 2000, 4000, 8000]

        url = urljoin(self.base_url, endpoint)
        headers = {"Csrf-Token": self._csrf_token} if self._csrf_token else {}

        for attempt in range(max_retries):
            try:
                response = await self._client.post(url, json=payload, headers=headers)

                # 4xx errors are not retryable (client errors)
                if 400 <= response.status_code < 500:
                    error_data = response.json() if response.content else {}
                    raise OmadaClientError(
                        f"Client error {response.status_code}: {error_data.get('msg', response.text)}",
                        status_code=response.status_code,
                    )

                # 5xx errors are retryable (server errors)
                if response.status_code >= 500:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(backoff_ms[attempt] / 1000.0)
                        continue
                    raise OmadaRetryExhaustedError(
                        f"Server error after {max_retries} attempts: {response.status_code}"
                    )

                # Success response
                response.raise_for_status()
                data: dict[str, Any] = response.json()

                # Check Omada errorCode
                error_code = data.get("errorCode", 0)
                if error_code != 0:
                    # Retry on 5xxx error codes (server/transient errors)
                    if error_code >= 5000 and attempt < max_retries - 1:
                        await asyncio.sleep(backoff_ms[attempt] / 1000.0)
                        continue
                    raise OmadaClientError(
                        f"Omada error {error_code}: {data.get('msg', 'Unknown error')}"
                    )

                return data

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                # Retry on connection/timeout errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_ms[attempt] / 1000.0)
                    continue
                raise OmadaRetryExhaustedError(
                    f"Connection error after {max_retries} attempts: {e}"
                ) from e

        # Should not reach here, but satisfy type checker
        raise OmadaRetryExhaustedError(f"Exhausted {max_retries} attempts")
