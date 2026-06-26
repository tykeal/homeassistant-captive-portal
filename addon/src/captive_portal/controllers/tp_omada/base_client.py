# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Compatibility imports for the legacy TP-Omada HTTP client."""

from captive_portal.controllers.tp_omada.legacy_client import (
    OmadaAuthenticationError,
    OmadaClientError,
    OmadaLegacyClient,
    OmadaRetryExhaustedError,
    discover_controller_id,
)

OmadaClient = OmadaLegacyClient

__all__ = [
    "OmadaAuthenticationError",
    "OmadaClient",
    "OmadaClientError",
    "OmadaLegacyClient",
    "OmadaRetryExhaustedError",
    "discover_controller_id",
]
