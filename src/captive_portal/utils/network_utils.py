# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Network utility functions for client IP detection and validation."""

import ipaddress
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
