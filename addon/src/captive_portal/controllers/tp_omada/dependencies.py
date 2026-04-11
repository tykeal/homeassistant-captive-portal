# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependency for per-request OmadaAdapter construction.

Each request gets a fresh ``OmadaClient`` + ``OmadaAdapter`` built from
the ``omada_config`` dict stored on ``app.state`` during lifespan startup.
This avoids shared async session state races caused by ``__aenter__``
mutating a shared client instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from captive_portal.controllers.tp_omada.adapter import OmadaAdapter
from captive_portal.controllers.tp_omada.base_client import OmadaClient


def get_omada_adapter(request: Request) -> OmadaAdapter | None:
    """Construct a per-request OmadaAdapter from app state config.

    Reads ``omada_config`` from ``request.app.state``.  When the config
    dict is present, a fresh ``OmadaClient`` and ``OmadaAdapter`` are
    constructed and returned.  When absent or ``None``, returns ``None``
    so callers can degrade gracefully (no controller configured).

    Args:
        request: The incoming FastAPI request.

    Returns:
        A freshly constructed ``OmadaAdapter``, or ``None`` when the
        Omada controller is not configured.
    """
    omada_config: dict[str, Any] | None = getattr(request.app.state, "omada_config", None)
    if omada_config is None:
        return None

    client = OmadaClient(
        base_url=omada_config["base_url"],
        controller_id=omada_config["controller_id"],
        username=omada_config["username"],
        password=omada_config["password"],
        verify_ssl=omada_config["verify_ssl"],
    )
    return OmadaAdapter(client=client, site_id=omada_config["site_id"])
