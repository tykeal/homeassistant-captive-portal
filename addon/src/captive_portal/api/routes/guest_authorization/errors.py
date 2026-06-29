# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Guest authorization error sanitization and security headers."""

from __future__ import annotations

from typing import TypeVar

from starlette.responses import Response

ResponseT = TypeVar("ResponseT", bound=Response)


def _strip_html_tags(message: str) -> str:
    """Strip HTML-like tags with a linear scan."""
    stripped_parts: list[str] = []
    cursor = 0

    while True:
        start = message.find("<", cursor)
        if start == -1:
            stripped_parts.append(message[cursor:])
            break

        end = message.find(">", start + 1)
        if end == -1:
            stripped_parts.append(message[cursor:])
            break

        stripped_parts.append(message[cursor:start])
        cursor = end + 1

    return "".join(stripped_parts)


def add_security_headers(response: ResponseT) -> ResponseT:
    """Add the current route-level guest security headers to a response.

    Args:
        response: Guest route response to mutate.

    Returns:
        The same response with security headers applied.
    """
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'"
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def sanitize_error_message(message: str | None) -> str:
    """Sanitize a guest-visible error message using the current rules.

    Args:
        message: Raw optional error message.

    Returns:
        Sanitized message safe for template rendering.
    """
    if not message:
        return "An error occurred. Please try again."

    if len(message) > 500:
        message = message[:500] + "..."

    message = _strip_html_tags(message)
    return message.strip() or "An error occurred. Please try again."
