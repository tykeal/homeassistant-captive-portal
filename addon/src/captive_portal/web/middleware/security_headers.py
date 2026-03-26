# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Security headers middleware for all HTTP responses."""

from __future__ import annotations

from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses.

    Args:
        app: ASGI application.
        frame_options: Value for X-Frame-Options header.
            Defaults to ``"SAMEORIGIN"`` (HA ingress framing).
        csp: Content-Security-Policy header value. When provided,
            always overrides any CSP set by route handlers.
            When ``None`` (default), a built-in CSP is applied
            only if no route handler has set one.
    """

    def __init__(
        self,
        app: Any,
        frame_options: str = "SAMEORIGIN",
        csp: str | None = None,
    ) -> None:
        """Initialise middleware with optional security policy overrides.

        Args:
            app: ASGI application.
            frame_options: Value for ``X-Frame-Options`` header.
            csp: Explicit ``Content-Security-Policy`` value or ``None``.
        """
        super().__init__(app)
        self._frame_options = frame_options
        self._csp = csp

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and add security headers to response."""
        response: Response = await call_next(request)

        # Prevent clickjacking — configurable for different listener policies
        response.headers["X-Frame-Options"] = self._frame_options

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Additional security headers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        if self._csp is not None:
            # Explicit CSP always overrides route-level CSP
            response.headers["Content-Security-Policy"] = self._csp
        elif "Content-Security-Policy" not in response.headers:
            # Default CSP: only set when no route handler has provided one
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'self'"
            )
            response.headers["Content-Security-Policy"] = csp

        # Permissions Policy - disable unnecessary features
        permissions = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )
        response.headers["Permissions-Policy"] = permissions

        return response
