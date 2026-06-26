# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependency for per-request Omada adapter construction.

Each request gets a fresh ``OmadaClient`` + ``OmadaAdapter`` built from
the ``omada_config`` dict stored on ``app.state`` during lifespan startup.
This avoids shared async session state races caused by ``__aenter__``
mutating a shared client instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from captive_portal.controllers.tp_omada.adapter_factory import OmadaRuntimeConfig
from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter
from captive_portal.controllers.tp_omada.legacy_client import OmadaLegacyClient
from captive_portal.controllers.tp_omada.openapi_adapter import OmadaOpenApiAdapter
from captive_portal.controllers.tp_omada.openapi_client import OpenApiClient


def get_omada_adapter(request: Request) -> OmadaControllerAdapter | None:
    """Construct a per-request Omada adapter from app state config.

    Reads ``omada_config`` from ``request.app.state``.  When the config
    dict is present, a fresh ``OmadaClient`` and ``OmadaAdapter`` are
    constructed and returned.  When absent or ``None``, returns ``None``
    so callers can degrade gracefully (no controller configured).

    Args:
        request: The incoming FastAPI request.

    Returns:
        A freshly constructed adapter, or ``None`` when the
        Omada controller is not configured.
    """
    omada_config: OmadaRuntimeConfig | dict[str, Any] | None = getattr(
        request.app.state, "omada_config", None
    )
    if omada_config is None:
        return None
    if isinstance(omada_config, OmadaRuntimeConfig):
        if omada_config.selected_backend == "openapi":
            openapi_client = OpenApiClient(
                base_url=omada_config.base_url,
                controller_id=omada_config.controller_id,
                client_id=omada_config.client_id,
                client_secret=omada_config.client_secret,
                verify_ssl=omada_config.verify_ssl,
                token_state=omada_config.token_state,
            )
            return OmadaOpenApiAdapter(
                client=openapi_client,
                site_name=omada_config.site_name,
                site_cache=omada_config.site_cache,
            )
        legacy_client = OmadaLegacyClient(
            base_url=omada_config.base_url,
            controller_id=omada_config.controller_id,
            username=omada_config.username,
            password=omada_config.password,
            verify_ssl=omada_config.verify_ssl,
        )
        return OmadaLegacyAdapter(client=legacy_client, site_id=omada_config.site_name)

    compatibility_client = OmadaLegacyClient(
        base_url=omada_config["base_url"],
        controller_id=omada_config["controller_id"],
        username=omada_config["username"],
        password=omada_config["password"],
        verify_ssl=omada_config["verify_ssl"],
    )
    return OmadaLegacyAdapter(client=compatibility_client, site_id=omada_config["site_id"])
