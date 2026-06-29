# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Focused TP-Omada client and adapter error-path tests."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from captive_portal.controllers.tp_omada.base_client import (
    OmadaAuthenticationError,
    OmadaClientError,
    OmadaRetryExhaustedError,
)
from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter
from captive_portal.controllers.tp_omada.legacy_client import OmadaLegacyClient
from captive_portal.controllers.tp_omada.openapi_adapter import (
    OmadaOpenApiAdapter,
    OpenApiSiteCache,
)
from captive_portal.controllers.tp_omada.openapi_client import (
    OpenApiClient,
    OpenApiTokenState,
    _status_code_from_error_code,
)


def _token_response(token: str = "token") -> httpx.Response:
    """Return a successful OpenAPI token response."""
    return httpx.Response(
        200,
        json={"errorCode": 0, "result": {"accessToken": token, "expiresIn": 7200}},
    )


def _legacy_response(
    payload: dict[str, object],
    *,
    status_code: int = 200,
    cookie_name: str = "TPOMADA_SESSIONID",
) -> MagicMock:
    """Build a legacy controller response mock."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    response.cookies = {cookie_name: "session-id"}
    response.content = b"{}"
    response.text = "response text"
    return response


def _legacy_client_with_http(http_client: MagicMock | AsyncMock) -> OmadaLegacyClient:
    """Return a legacy client wired to a mocked async HTTP client."""
    client = OmadaLegacyClient(
        base_url="https://ctrl.test:8043",
        controller_id="ctrl",
        username="operator",
        password="secret",
    )
    client._client = http_client
    return client


@pytest.mark.asyncio
async def test_openapi_active_client_requires_context() -> None:
    """OpenAPI client refuses use outside an initialized session."""
    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
    )

    with pytest.raises(OmadaClientError):
        client._active_client()


@pytest.mark.asyncio
async def test_openapi_token_request_error_is_authentication_error() -> None:
    """Transport failures during token fetch are authentication failures."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Raise a transport error for the token request."""
        raise httpx.ReadError("broken pipe", request=request)

    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OmadaAuthenticationError, match="ReadError"):
        await client.get_access_token()


@pytest.mark.asyncio
async def test_openapi_token_invalid_json_and_missing_token_raise() -> None:
    """Malformed token payloads and empty access tokens are rejected."""

    def bad_json_handler(_request: httpx.Request) -> httpx.Response:
        """Return invalid JSON from the token endpoint."""
        return httpx.Response(200, content=b"not-json")

    def missing_token_handler(_request: httpx.Request) -> httpx.Response:
        """Return a token response without an access token."""
        return httpx.Response(200, json={"errorCode": 0, "result": {}})

    bad_json_client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(bad_json_handler),
    )
    missing_token_client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(missing_token_handler),
    )

    with pytest.raises(OmadaAuthenticationError, match="not valid JSON"):
        await bad_json_client.get_access_token()
    with pytest.raises(OmadaAuthenticationError, match="omitted access token"):
        await missing_token_client.get_access_token()


@pytest.mark.asyncio
async def test_openapi_empty_cache_after_token_post_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token post that does not populate cache is treated as auth failure."""
    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
    )

    async def noop_post_token(_grant_type: str) -> None:
        """Leave token state empty to exercise the defensive cache check."""

    monkeypatch.setattr(client, "_post_token", noop_post_token)

    with pytest.raises(OmadaAuthenticationError, match="cache was not populated"):
        await client.get_access_token()


@pytest.mark.asyncio
async def test_openapi_auth_refresh_falls_back_to_client_credentials() -> None:
    """Failed refresh-token grants clear refresh state and retry client credentials."""
    grant_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Fail refresh grants and succeed client-credentials fallback."""
        grant_type = request.url.params["grant_type"]
        grant_types.append(grant_type)
        if grant_type == "refresh_token":
            return httpx.Response(200, json={"errorCode": 1})
        return _token_response("fallback-token")

    token_state = OpenApiTokenState(
        access_token="stale",
        refresh_token="refresh",
        expires_at_monotonic=time.monotonic() + 7200,
    )
    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        token_state=token_state,
        transport=httpx.MockTransport(handler),
    )

    await client.refresh_after_auth_failure()

    assert grant_types == ["refresh_token", "client_credentials"]
    assert token_state.access_token == "fallback-token"
    assert token_state.refresh_token is None


@pytest.mark.asyncio
async def test_openapi_request_json_body_and_invalid_json_response() -> None:
    """POST sends JSON bodies and invalid response JSON raises client errors."""
    captured_content: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token success and invalid JSON for the API call."""
        if request.url.path == "/openapi/authorize/token":
            return _token_response()
        captured_content.append(request.content)
        return httpx.Response(200, content=b"not-json")

    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OmadaClientError, match="not valid JSON"):
        await client.post("/openapi/v1/ctrl/sites/site/hotspot/clients/AA/auth", json_body={"x": 1})
    assert json.loads(captured_content[0]) == {"x": 1}


@pytest.mark.asyncio
async def test_openapi_auth_failure_on_last_retry_still_retries_after_refresh() -> None:
    """A final-attempt auth failure refreshes credentials and retries once."""
    api_calls = 0
    grant_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return transient failures, one auth failure, then success."""
        nonlocal api_calls
        if request.url.path == "/openapi/authorize/token":
            grant_types.append(request.url.params["grant_type"])
            token = "stale" if grant_types[-1] == "client_credentials" else "fresh"
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "result": {
                        "accessToken": token,
                        "refreshToken": "refresh",
                        "expiresIn": 7200,
                    },
                },
            )
        api_calls += 1
        if api_calls <= 3:
            return httpx.Response(503, json={"errorCode": 503})
        if api_calls == 4:
            return httpx.Response(401, json={"errorCode": 401})
        assert request.headers["Authorization"] == "AccessToken=fresh"
        return httpx.Response(200, json={"errorCode": 0, "result": {"ok": True}})

    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )

    with patch(
        "captive_portal.controllers.tp_omada.openapi_client.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        assert await client.get("/openapi/v1/ctrl/sites") == {
            "errorCode": 0,
            "result": {"ok": True},
        }
    assert grant_types == ["client_credentials", "refresh_token"]


@pytest.mark.asyncio
async def test_openapi_request_error_retries_then_exhausts() -> None:
    """Persistent OpenAPI transport errors exhaust retry attempts."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a token then raise on authenticated requests."""
        if request.url.path == "/openapi/authorize/token":
            return _token_response()
        raise httpx.ReadError("read failed", request=request)

    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )

    with patch(
        "captive_portal.controllers.tp_omada.openapi_client.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        with pytest.raises(OmadaRetryExhaustedError, match="ReadError"):
            await client.get("/openapi/v1/ctrl/sites")


@pytest.mark.asyncio
async def test_openapi_retry_exhausted_errors_are_not_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAPI retry-exhausted errors propagate directly."""
    token_state = OpenApiTokenState(
        access_token="fresh",
        expires_at_monotonic=time.monotonic() + 7200,
    )
    client = OpenApiClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        client_id="id",
        client_secret="secret",
        token_state=token_state,
    )

    async def fail_once(*_args: object, **_kwargs: object) -> dict[str, object]:
        """Raise a retry-exhausted error from a single request attempt."""
        raise OmadaRetryExhaustedError("already exhausted")

    monkeypatch.setattr(client, "_request_once", fail_once)

    with pytest.raises(OmadaRetryExhaustedError, match="already exhausted"):
        await client.get("/openapi/v1/ctrl/sites")


def test_openapi_error_code_status_mapping_variants() -> None:
    """OpenAPI errorCode mapping handles bools, strings, ints, and unknowns."""
    assert _status_code_from_error_code(True) == 400
    assert _status_code_from_error_code("404") == 404
    assert _status_code_from_error_code("not-an-int") == 400
    assert _status_code_from_error_code(object()) == 400
    assert _status_code_from_error_code(503) == 503
    assert _status_code_from_error_code(200) == 400


@pytest.mark.asyncio
async def test_legacy_authenticate_requires_initialized_client() -> None:
    """Legacy authentication refuses to run without an HTTP client."""
    client = OmadaLegacyClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        username="operator",
        password="secret",
    )

    with pytest.raises(OmadaClientError, match="not initialized"):
        await client._authenticate()


@pytest.mark.asyncio
async def test_legacy_authenticate_login_error_and_cookie_success() -> None:
    """Legacy login handles controller errors and alternate session cookies."""
    http_client = AsyncMock()
    client = _legacy_client_with_http(http_client)
    http_client.post.return_value = _legacy_response(
        {"errorCode": 12, "msg": "denied"},
    )

    with pytest.raises(OmadaAuthenticationError, match="denied"):
        await client._authenticate()

    http_client.post.return_value = _legacy_response(
        {"errorCode": 0, "result": {"token": "csrf"}},
        cookie_name="TPEAP_SESSIONID",
    )
    await client._authenticate()
    assert client._csrf_token == "csrf"

    http_client.post.return_value = _legacy_response(
        {"errorCode": 0, "result": {"token": "csrf"}},
        cookie_name="unexpected",
    )
    with pytest.raises(OmadaAuthenticationError, match="Session cookie"):
        await client._authenticate()


@pytest.mark.asyncio
async def test_legacy_authenticate_http_and_request_errors_are_wrapped() -> None:
    """Legacy login wraps status and transport exceptions."""
    request = httpx.Request("POST", "https://ctrl.test/ctrl/api/v2/hotspot/login")
    http_client = AsyncMock()
    status_response = _legacy_response({"errorCode": 0, "result": {"token": "csrf"}})
    status_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "forbidden",
        request=request,
        response=httpx.Response(403, request=request),
    )
    client = _legacy_client_with_http(http_client)
    http_client.post.return_value = status_response

    with pytest.raises(OmadaAuthenticationError, match="HTTP 403"):
        await client._authenticate()

    http_client.post.side_effect = httpx.ConnectError("refused", request=request)
    with pytest.raises(OmadaAuthenticationError, match="Connection error"):
        await client._authenticate()


@pytest.mark.asyncio
async def test_legacy_post_with_retry_edge_paths() -> None:
    """Legacy retry handles uninitialized, server, Omada, timeout, and zero tries."""
    uninitialized = OmadaLegacyClient(
        base_url="https://ctrl.test",
        controller_id="ctrl",
        username="operator",
        password="secret",
    )
    with pytest.raises(OmadaClientError, match="not initialized"):
        await uninitialized.post_with_retry("/endpoint", {})

    http_client = AsyncMock()
    client = _legacy_client_with_http(http_client)
    http_client.post.return_value = _legacy_response({}, status_code=503)
    with pytest.raises(OmadaRetryExhaustedError, match="Server error"):
        await client.post_with_retry("/endpoint", {}, max_retries=1)

    http_client.post.side_effect = [
        _legacy_response({"errorCode": 5001, "msg": "transient"}),
        _legacy_response({"errorCode": 0, "result": {"ok": True}}),
    ]
    with patch(
        "captive_portal.controllers.tp_omada.legacy_client.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        assert await client.post_with_retry("/endpoint", {}, max_retries=2) == {
            "errorCode": 0,
            "result": {"ok": True},
        }

    http_client.post.side_effect = None
    http_client.post.return_value = _legacy_response({"errorCode": 4001, "msg": "bad request"})
    with pytest.raises(OmadaClientError, match="bad request"):
        await client.post_with_retry("/endpoint", {}, max_retries=1)

    http_client.post.side_effect = httpx.TimeoutException("slow")
    with pytest.raises(OmadaRetryExhaustedError, match="Timeout"):
        await client.post_with_retry("/endpoint", {}, max_retries=1)

    with pytest.raises(OmadaRetryExhaustedError, match="Exhausted 0"):
        await client.post_with_retry("/endpoint", {}, max_retries=0)


@pytest.mark.asyncio
async def test_legacy_adapter_limits_update_and_status_paths() -> None:
    """Legacy adapter covers optional limits, update, and status fallback."""
    posted: list[tuple[str, dict[str, object]]] = []
    client = MagicMock()
    client.controller_id = "ctrl"
    client._client = SimpleNamespace(is_closed=False)

    async def post_with_retry(endpoint: str, payload: dict[str, object]) -> dict[str, object]:
        """Capture legacy adapter payloads."""
        posted.append((endpoint, payload))
        if endpoint.endswith("/session"):
            return {"result": {"authorized": True, "remainingTime": 120}}
        return {"result": {"authorized": True, "clientId": "grant-1"}}

    client.post_with_retry = post_with_retry
    adapter = OmadaLegacyAdapter(client=client, site_id="Default")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    result = await adapter.authorize(
        "AA:BB:CC:DD:EE:FF",
        expires_at,
        upload_limit_kbps=100,
        download_limit_kbps=200,
    )
    await adapter.update("AA:BB:CC:DD:EE:FF", expires_at)
    status = await adapter.get_status("AA:BB:CC:DD:EE:FF")

    assert result["grant_id"] == "grant-1"
    assert posted[0][1]["upKbps"] == 100
    assert posted[0][1]["downKbps"] == 200
    assert status == {"mac": "AA:BB:CC:DD:EE:FF", "authorized": True, "remaining_seconds": 120}

    async def failing_post(_endpoint: str, _payload: dict[str, object]) -> dict[str, object]:
        """Raise to exercise best-effort status fallback."""
        raise RuntimeError("unsupported")

    client.post_with_retry = failing_post
    assert await adapter.get_status("AA:BB:CC:DD:EE:FF") == {
        "mac": "AA:BB:CC:DD:EE:FF",
        "authorized": False,
        "remaining_seconds": 0,
    }


@pytest.mark.asyncio
async def test_openapi_adapter_update_revoke_and_status_edges() -> None:
    """OpenAPI adapter covers update, non-404 revoke, and status parsing edges."""
    future_end = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    client = MagicMock()
    client.controller_id = "ctrl"
    client.post = AsyncMock()
    client.get = AsyncMock(
        return_value={
            "errorCode": 0,
            "result": {
                "data": [
                    {"mac": "invalid"},
                    {
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "valid": False,
                        "end": future_end,
                    },
                ],
                "totalPage": 1,
            },
        },
    )
    adapter = OmadaOpenApiAdapter(
        client=client,
        site_cache=OpenApiSiteCache(site_name="Default", site_id="site-1"),
    )

    assert await adapter.update("AA:BB:CC:DD:EE:FF", datetime.now(timezone.utc)) == {
        "grant_id": "AA:BB:CC:DD:EE:FF",
        "status": "active",
        "mac": "AA:BB:CC:DD:EE:FF",
    }
    status = await adapter.get_status("AA:BB:CC:DD:EE:FF")
    assert status["authorized"] is False
    assert status["remaining_seconds"] > 0

    client.post.side_effect = OmadaClientError("boom", status_code=500)
    with pytest.raises(OmadaClientError, match="boom"):
        await adapter.revoke("AA:BB:CC:DD:EE:FF")


@pytest.mark.asyncio
async def test_openapi_adapter_status_paginates_until_match() -> None:
    """OpenAPI status lookup advances pages until it finds a matching record."""
    client = MagicMock()
    client.controller_id = "ctrl"
    client.get = AsyncMock(
        side_effect=[
            {"errorCode": 0, "result": {"data": [], "totalPage": 2}},
            {
                "errorCode": 0,
                "result": {
                    "data": [{"mac": "AA:BB:CC:DD:EE:FF"}],
                    "totalPage": 2,
                },
            },
        ],
    )
    adapter = OmadaOpenApiAdapter(
        client=client,
        site_cache=OpenApiSiteCache(site_name="Default", site_id="site-1"),
    )

    assert await adapter.get_status("AA:BB:CC:DD:EE:FF") == {
        "mac": "AA:BB:CC:DD:EE:FF",
        "authorized": True,
        "remaining_seconds": 0,
    }
