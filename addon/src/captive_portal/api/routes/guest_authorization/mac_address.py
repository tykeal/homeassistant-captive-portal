# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""MAC address extraction for guest authorization requests."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from captive_portal.utils.network_utils import validate_mac_address


def extract_mac_address(request: Request, form_mac: str | None = None) -> str:
    """Extract and validate a guest MAC address using the current priority order.

    Args:
        request: Incoming FastAPI request.
        form_mac: MAC address supplied by form data or query alias.

    Returns:
        Validated and normalized MAC address.

    Raises:
        HTTPException: When no MAC address exists or the value is invalid.
    """
    mac = request.headers.get("X-MAC-Address")
    if not mac:
        mac = request.headers.get("X-Client-Mac") or request.headers.get("Client-MAC")

    if not mac and form_mac and isinstance(form_mac, str) and form_mac.strip():
        mac = form_mac.strip()

    if not mac:
        mac = request.query_params.get("clientMac")

    if not mac:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine device MAC address. "
            "Please ensure you're connecting through the captive portal.",
        )

    try:
        return validate_mac_address(mac)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MAC address format: {exc}",
        ) from exc
