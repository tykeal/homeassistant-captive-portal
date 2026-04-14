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

from captive_portal.models.omada_config import OmadaConfig
from captive_portal.security.credential_encryption import decrypt_credential

_CONTROLLER_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{12,64}$")


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
    config: OmadaConfig,
    logger: logging.Logger,
) -> dict[str, Any] | None:
    """Build Omada configuration dict, auto-discovering controller ID if needed.

    The encrypted password is decrypted to produce the plaintext
    needed by the Omada client.

    Args:
        config: OmadaConfig DB model.
        logger: Logger instance for diagnostics.

    Returns:
        Omada config dict or ``None`` if not configured.
    """
    if not config.omada_configured:
        return None

    controller_url = config.controller_url.strip()
    username = config.username.strip()
    try:
        password = decrypt_credential(config.encrypted_password)
    except Exception as exc:
        logger.error("Failed to decrypt Omada password: %s", exc)
        return None
    site_name = config.site_name.strip()
    controller_id = config.controller_id.strip()
    verify_ssl = config.verify_ssl

    base_url = controller_url

    if not controller_id:
        from captive_portal.controllers.tp_omada.base_client import (
            OmadaClientError,
            discover_controller_id,
        )

        try:
            controller_id = await discover_controller_id(
                base_url=base_url,
                verify_ssl=verify_ssl,
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
    except ValueError as exc:
        logger.error(
            "Omada controller ID failed validation: %r: %s",
            controller_id,
            exc,
        )
        return None

    return {
        "base_url": base_url,
        "controller_id": controller_id,
        "username": username,
        "password": password,
        "verify_ssl": verify_ssl,
        "site_id": site_name,
    }
