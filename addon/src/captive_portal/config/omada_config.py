# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Shared Omada controller configuration builder.

Centralises the auto-discovery and config-dict construction that both
the admin and guest lifespans need so the logic lives in exactly one
place.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from captive_portal.config.settings import AppSettings

_CONTROLLER_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{16,64}$")


def _validate_controller_id(controller_id: str) -> str:
    """Validate controller ID is a safe hex string.

    Args:
        controller_id: Raw controller ID value.

    Returns:
        Stripped, validated controller ID.

    Raises:
        ValueError: If the ID does not match the expected hex pattern.
    """
    stripped = controller_id.strip()
    if not _CONTROLLER_ID_PATTERN.match(stripped):
        raise ValueError(f"Invalid controller ID format: expected hex string, got '{stripped}'")
    return stripped


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

    base_url = settings.omada_controller_url.strip()

    if not controller_id:
        from captive_portal.controllers.tp_omada.base_client import (
            OmadaClientError,
            discover_controller_id,
        )

        try:
            controller_id = await discover_controller_id(
                base_url=base_url,
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
                base_url,
                exc,
            )
            return None

    try:
        controller_id = _validate_controller_id(controller_id)
    except ValueError:
        logger.error(
            "Omada controller ID failed validation: %r",
            controller_id,
        )
        return None

    return {
        "base_url": base_url,
        "controller_id": controller_id,
        "username": settings.omada_username.strip(),
        "password": settings.omada_password,
        "verify_ssl": settings.omada_verify_ssl,
        "site_id": settings.omada_site_name.strip(),
    }
