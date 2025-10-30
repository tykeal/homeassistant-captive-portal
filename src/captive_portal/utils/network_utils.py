# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Network utility functions for client IP detection and validation."""

import ipaddress
import re
from typing import Optional

from fastapi import Request


def get_client_ip(
    request: Request,
    trust_proxies: bool = False,
    trusted_networks: Optional[list[str]] = None,
) -> str:
    """
    Extract the real client IP address from a request.

    Handles proxy scenarios correctly by checking X-Forwarded-For headers
    only when the request comes from a trusted proxy network.

    Args:
        request: FastAPI request object
        trust_proxies: Whether to trust X-Forwarded-For headers
        trusted_networks: List of CIDR networks to trust (e.g., ["10.0.0.0/8"])

    Returns:
        Client IP address as string

    Notes:
        - If trust_proxies is False, always returns direct connection IP
        - If trust_proxies is True, checks if connection is from trusted network
        - Takes leftmost IP from X-Forwarded-For (the original client)
        - Falls back to connection IP if headers are invalid or not trusted
    """
    # Get the direct connection IP
    direct_ip = request.client.host if request.client else "unknown"

    if not trust_proxies or direct_ip == "unknown":
        return direct_ip

    # Validate that the connection is from a trusted proxy
    if trusted_networks:
        try:
            client_addr = ipaddress.ip_address(direct_ip)
            is_trusted = any(client_addr in ipaddress.ip_network(net) for net in trusted_networks)
            if not is_trusted:
                # Connection is not from a trusted proxy, use direct IP
                return direct_ip
        except ValueError:
            # Invalid IP address, fall back to direct IP
            return direct_ip

    # Check for X-Forwarded-For header (most common)
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # Take the leftmost IP (original client) from the proxy chain
        # Format: "client, proxy1, proxy2"
        client_ip = xff.split(",")[0].strip()
        # Validate it's a valid IP
        try:
            ipaddress.ip_address(client_ip)
            return client_ip
        except ValueError:
            pass  # Invalid IP, fall through to other checks

    # Check for X-Real-IP header (used by some proxies like nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        try:
            ipaddress.ip_address(real_ip)
            return real_ip
        except ValueError:
            pass

    # No valid proxy headers found, use direct connection IP
    return direct_ip


def validate_mac_address(mac: str) -> str:
    """
    Validate and normalize MAC address format.

    Accepts MAC addresses in various common formats:
    - Colon-separated: AA:BB:CC:DD:EE:FF or aa:bb:cc:dd:ee:ff
    - Hyphen-separated: AA-BB-CC-DD-EE-FF or aa-bb-cc-dd-ee-ff
    - Dot-separated (Cisco): AABB.CCDD.EEFF or aabb.ccdd.eeff
    - Unseparated: AABBCCDDEEFF or aabbccddeeff

    Returns normalized MAC address in uppercase colon-separated format.

    Args:
        mac: MAC address string in any common format

    Returns:
        Normalized MAC address (uppercase, colon-separated)

    Raises:
        ValueError: If MAC address format is invalid

    Examples:
        >>> validate_mac_address("aa:bb:cc:dd:ee:ff")
        'AA:BB:CC:DD:EE:FF'
        >>> validate_mac_address("AA-BB-CC-DD-EE-FF")
        'AA:BB:CC:DD:EE:FF'
        >>> validate_mac_address("aabb.ccdd.eeff")
        'AA:BB:CC:DD:EE:FF'
    """
    if not mac:
        raise ValueError("MAC address cannot be empty")

    # Remove common separators to get raw hex string
    cleaned = mac.replace(":", "").replace("-", "").replace(".", "").upper()

    # Validate: must be exactly 12 hex characters
    if not re.match(r"^[0-9A-F]{12}$", cleaned):
        raise ValueError(
            f"Invalid MAC address format: '{mac}'. "
            "Expected 6 octets (12 hex characters) with optional separators."
        )

    # Format as colon-separated uppercase
    # Split into pairs: AABBCCDDEEFF -> [AA, BB, CC, DD, EE, FF]
    octets = [cleaned[i : i + 2] for i in range(0, 12, 2)]
    return ":".join(octets)
