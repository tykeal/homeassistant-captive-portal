# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Omada OpenAPI HTTP client and token cache."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx

from captive_portal.controllers.tp_omada.base_client import (
    OmadaAuthenticationError,
    OmadaClientError,
    OmadaRetryExhaustedError,
)


@dataclass
class OpenApiTokenState:
    """Shared in-memory OpenAPI token state.

    Attributes:
        access_token: Current access token or ``None``.
        refresh_token: Current refresh token or ``None``.
        expires_at_monotonic: Monotonic deadline for token expiry.
        lock: Async lock guarding single-flight refresh.
    """

    access_token: str | None = None
    refresh_token: str | None = None
    expires_at_monotonic: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class OpenApiClient:
    """Async HTTP client for the TP-Link Omada documented OpenAPI."""

    def __init__(
        self,
        *,
        base_url: str,
        controller_id: str,
        client_id: str,
        client_secret: str,
        verify_ssl: bool = True,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        token_state: OpenApiTokenState | None = None,
        refresh_margin_seconds: int = 300,
    ) -> None:
        """Initialize an OpenAPI client.

        Args:
            base_url: Omada controller base URL.
            controller_id: Omada controller ID (``omadacId``).
            client_id: OpenAPI application client ID.
            client_secret: OpenAPI application client secret.
            verify_ssl: Whether to verify TLS certificates.
            timeout: Request timeout in seconds.
            transport: Optional httpx transport for tests.
            token_state: Optional shared token cache.
            refresh_margin_seconds: Seconds before expiry to refresh.
        """
        self.base_url = base_url.rstrip("/")
        self.controller_id = controller_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.transport = transport
        self.token_state = token_state or OpenApiTokenState()
        self.refresh_margin_seconds = refresh_margin_seconds

    def _timeout(self) -> httpx.Timeout:
        """Return a bounded httpx timeout configuration.

        Returns:
            httpx timeout with a bounded connect timeout.
        """
        return httpx.Timeout(self.timeout, connect=min(self.timeout, 3.0))

    def _url(self, path: str) -> str:
        """Build an absolute controller URL.

        Args:
            path: Absolute OpenAPI path.

        Returns:
            Absolute URL string.
        """
        return urljoin(self.base_url + "/", path.lstrip("/"))

    async def _post_token(self, grant_type: str) -> None:
        """Request and cache an OpenAPI token.

        Args:
            grant_type: OAuth-style grant type.

        Raises:
            OmadaAuthenticationError: If token acquisition fails.
        """
        params: dict[str, str] = {"grant_type": grant_type}
        if grant_type == "refresh_token" and self.token_state.refresh_token:
            params["refreshToken"] = self.token_state.refresh_token
        payload = {
            "omadacId": self.controller_id,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout(),
                verify=self.verify_ssl,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    self._url("/openapi/authorize/token"),
                    params=params,
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise OmadaAuthenticationError(
                f"OpenAPI token request failed: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            raise OmadaAuthenticationError(
                "OpenAPI token request failed with HTTP status",
                status_code=response.status_code,
            )
        self._cache_token_response(response)

    def _cache_token_response(self, response: httpx.Response) -> None:
        """Parse a token response and update token state.

        Args:
            response: HTTP response from the token endpoint.

        Raises:
            OmadaAuthenticationError: If the token response is invalid.
        """
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise OmadaAuthenticationError("OpenAPI token response was not valid JSON") from exc
        if data.get("errorCode") != 0:
            raise OmadaAuthenticationError(
                f"OpenAPI token request failed with errorCode {data.get('errorCode')}"
            )
        result = data.get("result", {})
        access_token = result.get("accessToken")
        if not isinstance(access_token, str) or not access_token:
            raise OmadaAuthenticationError("OpenAPI token response omitted access token")
        refresh_token = result.get("refreshToken")
        expires_in = int(result.get("expiresIn", 7200))
        self.token_state.access_token = access_token
        self.token_state.refresh_token = refresh_token if isinstance(refresh_token, str) else None
        self.token_state.expires_at_monotonic = time.monotonic() + max(expires_in, 1)

    def _has_fresh_token(self) -> bool:
        """Return whether the cached token is outside the refresh margin.

        Returns:
            True when a non-expired access token can be reused.
        """
        if not self.token_state.access_token:
            return False
        refresh_at = self.token_state.expires_at_monotonic - self.refresh_margin_seconds
        return time.monotonic() < refresh_at

    async def get_access_token(self) -> str:
        """Return a valid OpenAPI access token, refreshing when needed.

        Returns:
            Access token string.
        """
        async with self.token_state.lock:
            if self._has_fresh_token() and self.token_state.access_token:
                return self.token_state.access_token
            grant_type = "refresh_token" if self.token_state.refresh_token else "client_credentials"
            await self._post_token(grant_type)
            if not self.token_state.access_token:
                raise OmadaAuthenticationError("OpenAPI token cache was not populated")
            return self.token_state.access_token

    async def auth_headers(self) -> dict[str, str]:
        """Return OpenAPI authentication headers.

        Returns:
            Authorization header using ``AccessToken=`` syntax.
        """
        return {"Authorization": f"AccessToken={await self.get_access_token()}"}

    async def get(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> dict[str, Any]:
        """Run an authenticated GET request.

        Args:
            path: OpenAPI path.
            params: Optional query parameters.

        Returns:
            Parsed Omada response payload.
        """
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run an authenticated POST request.

        Args:
            path: OpenAPI path.
            json_body: Optional JSON body. ``None`` sends no body.

        Returns:
            Parsed Omada response payload.
        """
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run an authenticated OpenAPI request with retry.

        Args:
            method: HTTP method.
            path: OpenAPI path.
            params: Optional query parameters.
            json_body: Optional JSON body.

        Returns:
            Parsed Omada response payload.
        """
        backoff_seconds = [1.0, 2.0, 4.0, 8.0]
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                return await self._request_once(method, path, params=params, json_body=json_body)
            except OmadaRetryExhaustedError:
                raise
            except OmadaClientError as exc:
                last_error = exc
                if exc.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
                await asyncio.sleep(backoff_seconds[attempt])
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == 3:
                    raise OmadaRetryExhaustedError(
                        f"OpenAPI request failed after retries: {type(exc).__name__}"
                    ) from exc
                await asyncio.sleep(backoff_seconds[attempt])
        raise OmadaRetryExhaustedError(f"OpenAPI retries exhausted: {type(last_error).__name__}")

    async def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one authenticated OpenAPI request.

        Args:
            method: HTTP method.
            path: OpenAPI path.
            params: Optional query parameters.
            json_body: Optional JSON body.

        Returns:
            Parsed Omada response payload.
        """
        async with httpx.AsyncClient(
            timeout=self._timeout(),
            verify=self.verify_ssl,
            transport=self.transport,
        ) as client:
            request_kwargs: dict[str, Any] = {
                "headers": await self.auth_headers(),
                "params": params,
            }
            if json_body is not None:
                request_kwargs["json"] = json_body
            response = await client.request(method, self._url(path), **request_kwargs)
        if response.status_code >= 500 or response.status_code == 429:
            raise OmadaClientError(
                f"OpenAPI transient HTTP status {response.status_code}",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise OmadaClientError(
                f"OpenAPI HTTP status {response.status_code}",
                status_code=response.status_code,
            )
        return self._parse_payload(response)

    def _parse_payload(self, response: httpx.Response) -> dict[str, Any]:
        """Parse and validate a non-token OpenAPI response.

        Args:
            response: HTTP response.

        Returns:
            Parsed JSON payload.

        Raises:
            OmadaClientError: If the response is invalid or failed.
        """
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise OmadaClientError("OpenAPI response was not valid JSON") from exc
        if data.get("errorCode", 0) != 0:
            code = data.get("errorCode")
            raise OmadaClientError(f"OpenAPI errorCode {code}", status_code=int(code or 400))
        return data
