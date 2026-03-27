# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant discovery error hierarchy.

All exceptions carry a safe ``user_message`` (never contains secrets)
and an optional ``detail`` for server-side diagnostics.
``str()`` always returns the safe message only.
"""


class HADiscoveryError(Exception):
    """Base exception for HA discovery operations."""

    def __init__(self, user_message: str, detail: str = "") -> None:
        """Initialize with a user-safe message and optional diagnostic detail.

        Args:
            user_message: Safe message suitable for end users (no secrets).
            detail: Full diagnostic information for server-side logging.
        """
        self.user_message = user_message
        self.detail = detail
        super().__init__(user_message)

    def __str__(self) -> str:
        """Return only the safe user message."""
        return self.user_message


class HAConnectionError(HADiscoveryError):
    """Raised when the HA API is unreachable."""


class HAAuthenticationError(HADiscoveryError):
    """Raised on HTTP 401 authentication failures."""


class HATimeoutError(HADiscoveryError):
    """Raised when an HA API request times out."""


class HAServerError(HADiscoveryError):
    """Raised on HTTP 5xx server errors from HA."""
