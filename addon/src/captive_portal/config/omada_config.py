# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Shared Omada controller configuration builder.

Centralises the auto-discovery and config-dict construction that both
the admin and guest lifespans need so the logic lives in exactly one
place.
"""

from __future__ import annotations

import logging
from typing import Any

from captive_portal.config.settings import AppSettings


async def build_omada_config(
    settings: AppSettings,
    logger: logging.Logger,
) -> dict[str, Any] | None:
    """Build Omada configuration dict, auto-discovering controller ID if needed.

    Args:
        settings: Application settings.
        logger: Logger instance for diagnostics.

    Returns:
        Omada config dict or ``None`` if not configured.
    """
    if not settings.omada_configured:
        return None

    controller_id = settings.omada_controller_id.strip()

    if not controller_id:
        from captive_portal.controllers.tp_omada.base_client import (
            OmadaClientError,
            discover_controller_id,
        )

        try:
            controller_id = await discover_controller_id(
                base_url=settings.omada_controller_url,
                verify_ssl=settings.omada_verify_ssl,
            )
            logger.info(
                "Auto-discovered Omada controller ID: %s",
                controller_id,
            )
        except OmadaClientError as exc:
            logger.error(
                "Failed to auto-discover Omada controller ID "
                "from %s — set omada_controller_id explicitly "
                "or check connectivity: %s",
                settings.omada_controller_url,
                exc,
            )
            return None

    return {
        "base_url": settings.omada_controller_url,
        "controller_id": controller_id,
        "username": settings.omada_username,
        "password": settings.omada_password,
        "verify_ssl": settings.omada_verify_ssl,
        "site_id": settings.omada_site_name,
    }
