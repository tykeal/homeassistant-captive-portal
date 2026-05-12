# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Security headers middleware for all HTTP responses."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Add security headers to all responses.

    Implemented as a pure ASGI middleware to avoid body-consumption
    bugs with Starlette's BaseHTTPMiddleware.

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
        app: ASGIApp,
        frame_options: str = "SAMEORIGIN",
        csp: str | None = None,
    ) -> None:
        """Initialise middleware with optional security policy overrides.

        Args:
            app: ASGI application.
            frame_options: Value for ``X-Frame-Options`` header.
            csp: Explicit ``Content-Security-Policy`` value or ``None``.
        """
        self._app = app
        self._frame_options = frame_options
        self._csp = csp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point — inject security headers on responses."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            """Inject security headers into response start messages."""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)

                # Prevent clickjacking
                headers["X-Frame-Options"] = self._frame_options

                # Prevent MIME type sniffing
                headers["X-Content-Type-Options"] = "nosniff"

                # Additional security headers
                headers["X-XSS-Protection"] = "1; mode=block"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

                # Content Security Policy
                if self._csp is not None:
                    # Explicit CSP always overrides route-level CSP
                    headers["Content-Security-Policy"] = self._csp
                elif "content-security-policy" not in headers:
                    # Default CSP: only set when no route handler
                    # has provided one
                    headers["Content-Security-Policy"] = (
                        "default-src 'self'; "
                        "script-src 'self'; "
                        "style-src 'self'; "
                        "img-src 'self' data:; "
                        "font-src 'self'; "
                        "connect-src 'self'; "
                        "frame-ancestors 'self'"
                    )

                # Cache-control headers for admin pages (FR-028)
                # Prevents back-button content leakage after logout
                if path == "/admin" or path.startswith("/admin/"):
                    headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                    headers["Pragma"] = "no-cache"
                    headers["Expires"] = "0"
                else:
                    # Guest portal: prevent CNA/browser caching
                    if path.startswith("/guest") and "cache-control" not in headers:
                        headers["Cache-Control"] = "no-store"

                # Permissions Policy - disable unnecessary features
                headers["Permissions-Policy"] = (
                    "geolocation=(), "
                    "microphone=(), "
                    "camera=(), "
                    "payment=(), "
                    "usb=(), "
                    "magnetometer=(), "
                    "gyroscope=(), "
                    "accelerometer=()"
                )

            await send(message)

        await self._app(scope, receive, send_wrapper)
