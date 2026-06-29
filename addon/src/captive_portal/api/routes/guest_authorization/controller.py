# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Omada metadata and controller authorization helpers for guest flows."""

from __future__ import annotations

import logging
import re

from captive_portal.controllers.tp_omada.adapter_protocol import OmadaControllerAdapter
from captive_portal.controllers.tp_omada.base_client import (
    OmadaClientError,
    OmadaRetryExhaustedError,
)
from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter
from captive_portal.models.access_grant import AccessGrant, GrantStatus

from .context import GuestOmadaParams

SITE_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{12,64}$")
_logger = logging.getLogger("captive_portal.guest")


def truncate(value: str | None, max_length: int) -> str | None:
    """Strip whitespace and truncate a value to ``max_length``.

    Args:
        value: Raw input string.
        max_length: Maximum retained length.

    Returns:
        Sanitized string, or None when the input is empty.
    """
    if not value or not value.strip():
        return None
    return value.strip()[:max_length]


def apply_site_override(
    site_from_form: str | None,
    current_site: str,
    pattern: re.Pattern[str] = SITE_ID_PATTERN,
) -> str:
    """Apply a valid Omada legacy site override.

    Args:
        site_from_form: Site identifier submitted by the controller.
        current_site: Current adapter site identifier.
        pattern: Validation pattern for accepted site identifiers.

    Returns:
        Submitted site when valid, otherwise ``current_site``.
    """
    if site_from_form and site_from_form.strip() and pattern.match(site_from_form.strip()):
        return site_from_form.strip()
    return current_site


def apply_omada_metadata(grant: AccessGrant, params: GuestOmadaParams) -> AccessGrant:
    """Store truncated Omada metadata on a grant.

    Args:
        grant: Grant to update.
        params: Submitted Omada metadata.

    Returns:
        The same grant with metadata fields updated.
    """
    grant.omada_gateway_mac = truncate(params.gateway_mac, 17)
    grant.omada_ap_mac = truncate(params.ap_mac, 17)
    grant.omada_vid = truncate(params.vid, 8)
    grant.omada_ssid_name = truncate(params.ssid_name, 64)
    grant.omada_radio_id = truncate(params.radio_id, 2)
    return grant


def apply_legacy_site_override(
    adapter: OmadaControllerAdapter | None,
    site: str | None,
) -> None:
    """Apply valid legacy Omada site override to legacy adapters only.

    Args:
        adapter: Optional configured controller adapter.
        site: Submitted site identifier.
    """
    if isinstance(adapter, OmadaLegacyAdapter):
        adapter.site_id = apply_site_override(site, adapter.site_id, SITE_ID_PATTERN)


async def authorize_with_controller(
    adapter: OmadaControllerAdapter | None,
    grant: AccessGrant,
    mac_address: str,
    gateway_mac: str | None = None,
    ap_mac: str | None = None,
    ssid_name: str | None = None,
    radio_id: str | None = None,
    vid: str | None = None,
) -> tuple[AccessGrant, str | None]:
    """Authorize a grant with the configured Omada controller.

    Args:
        adapter: Optional Omada controller adapter.
        grant: Pending grant to authorize.
        mac_address: Device MAC address.
        gateway_mac: Gateway MAC metadata.
        ap_mac: Access point MAC metadata.
        ssid_name: SSID name metadata.
        radio_id: Radio identifier metadata.
        vid: VLAN identifier metadata.

    Returns:
        Tuple of updated grant and diagnostic error detail, if any.
    """
    if adapter is None:
        grant.status = GrantStatus.ACTIVE
        return grant, None

    error_detail: str | None = None
    try:
        result = await adapter.authorize(
            mac=mac_address,
            expires_at=grant.end_utc,
            gateway_mac=gateway_mac,
            ap_mac=ap_mac,
            ssid_name=ssid_name,
            radio_id=radio_id,
            vid=vid,
        )
        grant.status = GrantStatus.ACTIVE
        grant.controller_grant_id = result.get("grant_id")
    except (OmadaClientError, OmadaRetryExhaustedError) as exc:
        _logger.error(
            "Controller authorization failed for MAC %s: %s",
            mac_address,
            exc,
        )
        grant.status = GrantStatus.FAILED
        error_detail = f"{type(exc).__name__}: {exc}"

    return grant, error_detail
