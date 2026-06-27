# SPDX-FileCopyrightText: 2026 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Guest listener debug logging middleware."""

from __future__ import annotations

import asyncio
import logging

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("captive_portal.guest")


class DebugLoggingMiddleware:
    """Log request/response details when debug_guest_portal is enabled.

    Implemented as a pure ASGI middleware to avoid the body-consumption
    bug that breaks Form() parsing when multiple BaseHTTPMiddleware
    subclasses are stacked.

    Args:
        app: ASGI application.
        debug_enabled: Activate debug logging when ``True``.
    """

    def __init__(self, app: ASGIApp, debug_enabled: bool = False) -> None:
        """Initialise with debug toggle.

        Args:
            app: ASGI application.
            debug_enabled: Whether to emit debug log lines.
        """
        self._app = app
        self._debug = debug_enabled

    @staticmethod
    def _wrap_receive(receive: Receive, method: str, path: str) -> Receive:
        """Create a logging wrapper around the ASGI receive callable.

        Args:
            receive: Original ASGI receive callable.
            method: HTTP method for log context.
            path: Request path for log context.

        Returns:
            A wrapped receive callable that logs each message.
        """

        async def receive_wrapper() -> Message:
            """Log each ASGI receive message before forwarding."""
            message = await receive()
            msg_type = message.get("type", "")
            if msg_type == "http.request":
                body_len = len(message.get("body", b""))
                more = message.get("more_body", False)
                logger.debug(
                    "RECEIVE  %s %s  type=%s  body_len=%d  more_body=%s",
                    method,
                    path,
                    msg_type,
                    body_len,
                    more,
                )
            elif msg_type == "http.disconnect":
                logger.warning(
                    "RECEIVE  %s %s  type=http.disconnect (client closed connection)",
                    method,
                    path,
                )
            else:
                logger.debug(
                    "RECEIVE  %s %s  type=%s",
                    method,
                    path,
                    msg_type,
                )
            return message

        return receive_wrapper

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point to log request/response when debug is active.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http" or not self._debug:
            await self._app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        headers = dict(
            (k.decode("latin-1"), v.decode("latin-1")) for k, v in scope.get("headers", [])
        )

        logger.debug(
            "REQUEST  %s %s  User-Agent=%s  Content-Type=%s  Origin=%s  Referer=%s",
            method,
            path,
            headers.get("user-agent", ""),
            headers.get("content-type", ""),
            headers.get("origin", ""),
            headers.get("referer", ""),
        )

        status_code = 0
        response_headers: dict[str, str] = {}

        async def send_wrapper(message: Message) -> None:
            """Capture response metadata and log before forwarding."""
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                response_headers = dict(
                    (
                        k.decode("latin-1").lower(),
                        v.decode("latin-1"),
                    )
                    for k, v in message.get("headers", [])
                )
                logger.debug(
                    "RESPONSE %s %s  status=%d  CSP=%s  X-Frame-Options=%s  Cache-Control=%s",
                    method,
                    path,
                    status_code,
                    response_headers.get("content-security-policy", ""),
                    response_headers.get("x-frame-options", ""),
                    response_headers.get("cache-control", ""),
                )
            await send(message)

        effective_receive: Receive = receive
        if method in {"POST", "PUT", "PATCH"}:
            effective_receive = self._wrap_receive(receive, method, path)

        try:
            await self._app(scope, effective_receive, send_wrapper)
        except ClientDisconnect:
            logger.warning(
                "CLIENT_DISCONNECT  %s %s  (body read failed — client closed connection)",
                method,
                path,
            )
            raise
        except asyncio.CancelledError:
            logger.warning(
                "REQUEST_CANCELLED  %s %s  (task cancelled — possible server shutdown or timeout)",
                method,
                path,
            )
            raise
        except Exception:
            logger.exception(
                "UNHANDLED_ERROR  %s %s",
                method,
                path,
            )
            raise
