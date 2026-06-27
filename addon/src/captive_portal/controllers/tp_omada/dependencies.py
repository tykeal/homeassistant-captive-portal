# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependency for Omada adapter construction.

Each request gets a fresh adapter for the backend selected during
lifespan startup.  Runtime configuration usually arrives as an
``OmadaRuntimeConfig`` on ``app.state``; legacy dict configs remain
supported for compatibility.
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


def build_omada_adapter(
    omada_config: OmadaRuntimeConfig | dict[str, Any] | None,
) -> OmadaControllerAdapter | None:
    """Construct an Omada adapter from runtime configuration.

    When a config is present, a fresh client and matching adapter are
    constructed and returned.  When absent or ``None``, returns ``None``
    so callers can degrade gracefully.

    Args:
        omada_config: Selected runtime config or legacy config mapping.

    Returns:
        A freshly constructed adapter, or ``None`` when the
        Omada controller is not configured.
    """
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


def get_omada_adapter(request: Request) -> OmadaControllerAdapter | None:
    """Construct a per-request Omada adapter from app state config.

    Reads ``omada_config`` from ``request.app.state`` and delegates to the
    shared adapter builder.  When absent or ``None``, returns ``None`` so
    callers can degrade gracefully.

    Args:
        request: The incoming FastAPI request.

    Returns:
        A freshly constructed adapter, or ``None`` when the
        Omada controller is not configured.
    """
    omada_config: OmadaRuntimeConfig | dict[str, Any] | None = getattr(
        request.app.state, "omada_config", None
    )
    return build_omada_adapter(omada_config)
