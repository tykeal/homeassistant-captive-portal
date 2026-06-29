# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Legacy TP-Omada HTTP client with authentication and retry logic."""

import asyncio
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

_ALLOWED_CONTROLLER_SCHEMES = frozenset({"http", "https"})


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


def _response_result(data: dict[str, Any]) -> dict[str, Any]:
    """Return normalized Omada response result payload.

    Args:
        data: Decoded Omada response payload.

    Returns:
        Result dictionary, or an empty dict when the result is missing or
        malformed.
    """
    result = data.get("result")
    if isinstance(result, dict):
        return result
    return {}


def validate_controller_base_url(base_url: str) -> str:
    """Validate and normalize an Omada controller base URL.

    Args:
        base_url: Raw controller base URL.

    Returns:
        The stripped controller base URL without trailing slashes.

    Raises:
        OmadaClientError: If the URL does not use HTTP(S), lacks a host,
            or is malformed.
    """
    stripped = base_url.strip()
    if any(char.isspace() or ord(char) < 0x20 or char == "\x7f" for char in stripped):
        raise OmadaClientError(
            "Invalid Omada controller URL: URL contains whitespace or control characters"
        )
    try:
        parsed = urlparse(stripped)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        _port = parsed.port
    except ValueError as exc:
        raise OmadaClientError(f"Invalid Omada controller URL: {exc}") from exc
    if scheme not in _ALLOWED_CONTROLLER_SCHEMES:
        raise OmadaClientError("Invalid Omada controller URL: scheme must be http or https")
    if not hostname:
        raise OmadaClientError("Invalid Omada controller URL: host is required")
    return stripped.rstrip("/")


class OmadaLegacyClient:
    """HTTP client for the legacy TP-Omada controller API with authentication.

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
        self.base_url = validate_controller_base_url(base_url)
        self.controller_id = controller_id
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self._client: Optional[httpx.AsyncClient] = None
        self._csrf_token: Optional[str] = None

    async def __aenter__(self) -> "OmadaLegacyClient":
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
            self._client = None

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

            csrf_token = _response_result(data).get("token")
            if not isinstance(csrf_token, str) or not csrf_token:
                raise OmadaAuthenticationError("CSRF token not found in login response")
            self._csrf_token = csrf_token

            # Extract session cookie (TPEAP_SESSIONID or TPOMADA_SESSIONID)
            cookies = response.cookies
            session_cookie = cookies.get("TPOMADA_SESSIONID") or cookies.get("TPEAP_SESSIONID")
            if not session_cookie:
                raise OmadaAuthenticationError("Session cookie not found in response")

        except httpx.HTTPStatusError as e:
            raise OmadaAuthenticationError(f"HTTP {e.response.status_code}: {e}") from e
        except httpx.RequestError as e:
            raise OmadaAuthenticationError(f"Connection error: {e}") from e

    async def post_with_retry(  # noqa: C901 - TODO: refactor to reduce complexity
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

            except httpx.ConnectError as e:
                # Retry on connection errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_ms[attempt] / 1000.0)
                    continue
                raise OmadaRetryExhaustedError(
                    f"Connection error after {max_retries} attempts: {e}"
                ) from e
            except httpx.TimeoutException as e:
                # Retry on timeout errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_ms[attempt] / 1000.0)
                    continue
                raise OmadaRetryExhaustedError(f"Timeout after {max_retries} attempts: {e}") from e

        # Should not reach here, but satisfy type checker
        raise OmadaRetryExhaustedError(f"Exhausted {max_retries} attempts")


async def discover_controller_id(
    base_url: str,
    verify_ssl: bool = True,
    timeout: float = 10.0,
) -> str:
    """Discover the Omada controller ID via the unauthenticated /api/info endpoint.

    Args:
        base_url: Controller base URL (e.g., https://controller:443)
        verify_ssl: Whether to verify SSL certificates
        timeout: HTTP request timeout in seconds

    Returns:
        The controller ID (omadacId)

    Raises:
        OmadaClientError: If discovery fails
    """
    validated_base_url = validate_controller_base_url(base_url)
    endpoint = "/api/info"
    request_path = endpoint.lstrip("/")
    discovery_timeout = httpx.Timeout(timeout, connect=min(timeout, 3.0))
    async with httpx.AsyncClient(
        base_url=f"{validated_base_url}/",
        timeout=discovery_timeout,
        verify=verify_ssl,
    ) as client:
        try:
            response = await client.get(request_path)
            response.raise_for_status()
            try:
                data: dict[str, Any] = response.json()
            except (ValueError, UnicodeDecodeError) as e:
                raise OmadaClientError(f"Invalid JSON from {endpoint}: {e}") from e
            if data.get("errorCode") != 0:
                raise OmadaClientError(
                    f"Controller info request failed at {endpoint}: "
                    f"{data.get('msg', 'Unknown error')}"
                )
            omadac_id = _response_result(data).get("omadacId")
            if not isinstance(omadac_id, str) or not omadac_id:
                raise OmadaClientError(f"omadacId not found in {endpoint} response")
            return omadac_id
        except httpx.HTTPStatusError as e:
            raise OmadaClientError(
                f"HTTP {e.response.status_code} from {endpoint}: {e}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise OmadaClientError(f"Connection error fetching {endpoint}: {e}") from e


OmadaClient = OmadaLegacyClient
