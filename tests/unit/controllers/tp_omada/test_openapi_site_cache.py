# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenAPI site discovery and caching."""

from __future__ import annotations

import httpx
import pytest

from captive_portal.controllers.tp_omada.base_client import OmadaClientError
from captive_portal.controllers.tp_omada.openapi_adapter import OmadaOpenApiAdapter
from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient


@pytest.mark.asyncio
async def test_site_discovery_pages_and_caches_match() -> None:
    """Site discovery pages until a matching name is found and caches it."""
    site_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token and paginated site-discovery responses."""
        nonlocal site_requests
        if request.url.path == "/openapi/authorize/token":
            return httpx.Response(
                200,
                json={"errorCode": 0, "result": {"accessToken": "token", "expiresIn": 7200}},
            )
        site_requests += 1
        page = request.url.params["page"]
        data = [] if page == "1" else [{"siteId": "site-2", "name": "Guest"}]
        return httpx.Response(
            200,
            json={"errorCode": 0, "result": {"data": data, "totalPage": 2}},
        )

    client = OpenApiClient(
        base_url="https://ctrl.test:8043",
        controller_id="0123456789ab",
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
    )
    adapter = OmadaOpenApiAdapter(client=client, site_name="Guest")

    assert await adapter.get_site_id() == "site-2"
    assert await adapter.get_site_id() == "site-2"
    assert site_requests == 2


@pytest.mark.asyncio
async def test_site_discovery_ignores_malformed_data() -> None:
    """Site discovery treats malformed data as no matching sites."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return token and malformed site-discovery data."""
        if request.url.path == "/openapi/authorize/token":
            return httpx.Response(
                200,
                json={"errorCode": 0, "result": {"accessToken": "token", "expiresIn": 7200}},
            )
        return httpx.Response(
            200,
            json={"errorCode": 0, "result": {"data": None, "totalPage": 1}},
        )

    client = OpenApiClient(
        base_url="https://ctrl.test:8043",
        controller_id="0123456789ab",
        client_id="client-id",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
    )
    adapter = OmadaOpenApiAdapter(client=client, site_name="Guest")

    with pytest.raises(OmadaClientError, match="site not found"):
        await adapter.get_site_id()
