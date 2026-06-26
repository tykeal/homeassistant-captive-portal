# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for Omada OpenAPI token handling."""

from __future__ import annotations

import time

import httpx
import pytest

from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient, OpenApiTokenState


@pytest.mark.asyncio
async def test_client_credentials_token_and_header() -> None:
    """Client credentials token requests use the documented contract."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a successful token response and capture the request."""
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "errorCode": 0,
                "result": {
                    "accessToken": "access-token",
                    "refreshToken": "refresh-token",
                    "expiresIn": 7200,
                },
            },
        )

    client = OpenApiClient(
        base_url="https://ctrl.test:8043",
        controller_id="0123456789ab",
        client_id="client-id",
        client_secret="client-secret",
        verify_ssl=False,
        transport=httpx.MockTransport(handler),
    )

    headers = await client.auth_headers()

    assert headers == {"Authorization": "AccessToken=access-token"}
    assert requests[0].url.path == "/openapi/authorize/token"
    assert requests[0].url.query == b"grant_type=client_credentials"
    assert requests[0].content == (
        b'{"omadacId":"0123456789ab","client_id":"client-id","client_secret":"client-secret"}'
    )


@pytest.mark.asyncio
async def test_refresh_token_before_expiry() -> None:
    """Refresh token grant is used when the cached token enters its margin."""
    grant_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return initial and refreshed token responses."""
        grant_types.append(request.url.params["grant_type"])
        token = "initial" if len(grant_types) == 1 else "refreshed"
        return httpx.Response(
            200,
            json={
                "errorCode": 0,
                "result": {
                    "accessToken": token,
                    "refreshToken": "refresh-token",
                    "expiresIn": 100,
                },
            },
        )

    client = OpenApiClient(
        base_url="https://ctrl.test:8043",
        controller_id="0123456789ab",
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
        refresh_margin_seconds=300,
    )

    assert await client.get_access_token() == "initial"
    assert await client.get_access_token() == "refreshed"
    assert grant_types == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_token_errors_redact_secret_and_token() -> None:
    """Exceptions do not include client secrets or returned token material."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return an error response containing sensitive material."""
        return httpx.Response(
            200,
            json={"errorCode": 1, "msg": "bad secret client-secret access-token"},
        )

    client = OpenApiClient(
        base_url="https://ctrl.test:8043",
        controller_id="0123456789ab",
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(Exception) as excinfo:
        await client.get_access_token()
    message = str(excinfo.value)
    assert "client-secret" not in message
    assert "access-token" not in message


@pytest.mark.asyncio
async def test_unauthorized_request_refreshes_token_once() -> None:
    """A stale token rejected by OpenAPI is refreshed and retried once."""
    seen_authorization: list[str] = []
    grant_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Reject the stale token, refresh it, then accept the retry."""
        if request.url.path == "/openapi/authorize/token":
            grant_types.append(request.url.params["grant_type"])
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "result": {
                        "accessToken": "fresh-token",
                        "refreshToken": "fresh-refresh",
                        "expiresIn": 7200,
                    },
                },
            )

        seen_authorization.append(request.headers["Authorization"])
        if len(seen_authorization) == 1:
            return httpx.Response(401, json={"errorCode": 401, "msg": "expired"})
        return httpx.Response(200, json={"errorCode": 0, "result": {"ok": True}})

    token_state = OpenApiTokenState(
        access_token="stale-token",
        refresh_token="refresh-token",
        expires_at_monotonic=time.monotonic() + 7200,
    )
    client = OpenApiClient(
        base_url="https://ctrl.test:8043",
        controller_id="0123456789ab",
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
        token_state=token_state,
    )

    assert await client.get("/openapi/v1/0123456789ab/sites") == {
        "errorCode": 0,
        "result": {"ok": True},
    }
    assert seen_authorization == [
        "AccessToken=stale-token",
        "AccessToken=fresh-token",
    ]
    assert grant_types == ["refresh_token"]
