# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Contract tests for Omada OpenAPI authorization flow."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from captive_portal.controllers.tp_omada.openapi_adapter import OmadaOpenApiAdapter
from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient


@pytest.mark.contract
@pytest.mark.asyncio
async def test_openapi_authorize_posts_documented_path_without_body() -> None:
    """OpenAPI authorize uses the documented auth endpoint without duration body."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token, site, and authorize responses."""
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
        return httpx.Response(200, json={"errorCode": 0, "msg": ""})

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

    result = await adapter.authorize(
        mac="aa:bb:cc:dd:ee:ff",
        expires_at=datetime.now(timezone.utc),
        gateway_mac="ignored",
        ap_mac="ignored",
    )

    auth_request = [request for request in requests if request.url.path.endswith("/auth")][0]
    assert auth_request.url.path == (
        "/openapi/v1/0123456789ab/sites/site-1/hotspot/clients/AA-BB-CC-DD-EE-FF/auth"
    )
    assert auth_request.content == b""
    assert auth_request.headers["Authorization"] == "AccessToken=token"
    assert result == {
        "grant_id": "AA:BB:CC:DD:EE:FF",
        "status": "active",
        "mac": "AA:BB:CC:DD:EE:FF",
    }
