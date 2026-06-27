# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for Omada OpenAPI revoke and status flows."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from captive_portal.controllers.tp_omada.openapi_adapter import OmadaOpenApiAdapter
from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient


def _adapter(requests: list[httpx.Request]) -> OmadaOpenApiAdapter:
    """Build an adapter with mocked token, site, revoke, and status responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token, site, status, and successful action responses."""
        requests.append(request)
        if request.url.path == "/openapi/authorize/token":
            return httpx.Response(
                200,
                json={"errorCode": 0, "result": {"accessToken": "token", "expiresIn": 7200}},
            )
        if request.url.path.endswith("/sites"):
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "result": {"data": [{"siteId": "site-1", "name": "Default"}]},
                },
            )
        if request.url.path.endswith("/authed-records"):
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "result": {"data": [{"mac": "AA-BB-CC-DD-EE-FF", "valid": True, "end": 0}]},
                },
            )
        return httpx.Response(200, json={"errorCode": 0})

    return OmadaOpenApiAdapter(
        client=OpenApiClient(
            base_url="https://ctrl.test:8043",
            controller_id="0123456789ab",
            client_id="client-id",
            client_secret="client-secret",
            transport=httpx.MockTransport(handler),
        ),
        site_name="Default",
    )


@pytest.mark.contract
@pytest.mark.asyncio
async def test_openapi_revoke_posts_unauth_without_body() -> None:
    """OpenAPI revoke calls the documented unauth endpoint."""
    requests: list[httpx.Request] = []
    result = await _adapter(requests).revoke(mac="AA:BB:CC:DD:EE:FF")
    unauth_request = [request for request in requests if request.url.path.endswith("/unauth")][0]
    assert unauth_request.content == b""
    assert result == {"success": True, "mac": "AA:BB:CC:DD:EE:FF"}


@pytest.mark.contract
@pytest.mark.asyncio
async def test_openapi_revoke_treats_not_found_as_success() -> None:
    """OpenAPI revoke is idempotent when a client is already unauthenticated."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token/site success and unauth not-found."""
        if request.url.path == "/openapi/authorize/token":
            return httpx.Response(
                200,
                json={"errorCode": 0, "result": {"accessToken": "token", "expiresIn": 7200}},
            )
        if request.url.path.endswith("/sites"):
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "result": {"data": [{"siteId": "site-1", "name": "Default"}]},
                },
            )
        return httpx.Response(404, json={"errorCode": 404, "msg": "not found"})

    adapter = OmadaOpenApiAdapter(
        client=OpenApiClient(
            base_url="https://ctrl.test:8043",
            controller_id="0123456789ab",
            client_id="client-id",
            client_secret="client-secret",
            transport=httpx.MockTransport(handler),
        ),
        site_name="Default",
    )

    assert await adapter.revoke(mac="AA:BB:CC:DD:EE:FF") == {
        "success": True,
        "mac": "AA:BB:CC:DD:EE:FF",
    }


@pytest.mark.contract
@pytest.mark.asyncio
async def test_openapi_status_and_update_semantics() -> None:
    """Status maps authed records and update does not send duration fields."""
    requests: list[httpx.Request] = []
    adapter = _adapter(requests)
    status = await adapter.get_status("aa:bb:cc:dd:ee:ff")
    updated = await adapter.update("aa:bb:cc:dd:ee:ff", datetime.now(timezone.utc))
    assert status["authorized"] is True
    assert status["remaining_seconds"] == 0
    assert updated["status"] == "active"
    assert all(b"duration" not in request.content for request in requests)


@pytest.mark.contract
@pytest.mark.asyncio
async def test_openapi_status_treats_malformed_records_as_absent() -> None:
    """Malformed authed-record data returns an unauthorized status."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token, site success, and malformed authed records."""
        if request.url.path == "/openapi/authorize/token":
            return httpx.Response(
                200,
                json={"errorCode": 0, "result": {"accessToken": "token", "expiresIn": 7200}},
            )
        if request.url.path.endswith("/sites"):
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "result": {"data": [{"siteId": "site-1", "name": "Default"}]},
                },
            )
        return httpx.Response(200, json={"errorCode": 0, "result": {"data": None}})

    adapter = OmadaOpenApiAdapter(
        client=OpenApiClient(
            base_url="https://ctrl.test:8043",
            controller_id="0123456789ab",
            client_id="client-id",
            client_secret="client-secret",
            transport=httpx.MockTransport(handler),
        ),
        site_name="Default",
    )

    assert await adapter.get_status("AA:BB:CC:DD:EE:FF") == {
        "authorized": False,
        "mac": "AA:BB:CC:DD:EE:FF",
        "remaining_seconds": 0,
    }
