# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for ASGI receive diagnostics in _DebugLoggingMiddleware."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from captive_portal.guest_app import _DebugLoggingMiddleware


async def _noop_send(message: Message) -> None:
    """No-op send callable for testing."""


def _make_scope(
    method: str = "POST",
    path: str = "/guest/authorize",
) -> Scope:
    """Build a minimal HTTP scope dict.

    Args:
        method: HTTP method.
        path: Request path.

    Returns:
        A scope dictionary suitable for ASGI testing.
    """
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"user-agent", b"CaptiveNetworkSupport"),
        ],
    }


def _make_receive(messages: list[Message]) -> Receive:
    """Build a receive callable that yields messages in order.

    Args:
        messages: Ordered ASGI messages to return.

    Returns:
        An async callable matching the ASGI Receive protocol.
    """
    it = iter(messages)

    async def receive() -> Message:
        """Return next ASGI message."""
        return next(it)

    return receive


def _make_app_that_reads_body() -> ASGIApp:
    """Build an ASGI app that reads the body via receive().

    Returns:
        An ASGI app that consumes the request body and sends
        a 200 response.
    """

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        """Read body and send a 200 response."""
        while True:
            msg = await receive()
            if msg.get("type") == "http.request":
                if not msg.get("more_body", False):
                    break
            else:
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    return app


def _make_disconnect_app() -> ASGIApp:
    """Build an ASGI app that raises ClientDisconnect.

    Returns:
        An ASGI app that always raises ClientDisconnect.
    """

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        """Raise ClientDisconnect unconditionally."""
        raise ClientDisconnect()

    return app


def _make_cancelled_app() -> ASGIApp:
    """Build an ASGI app that raises CancelledError.

    Returns:
        An ASGI app that always raises asyncio.CancelledError.
    """

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        """Raise CancelledError unconditionally."""
        raise asyncio.CancelledError()

    return app


def _make_error_app() -> ASGIApp:
    """Build an ASGI app that raises RuntimeError.

    Returns:
        An ASGI app that always raises RuntimeError.
    """

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        """Raise RuntimeError unconditionally."""
        raise RuntimeError("boom")

    return app


class TestReceiveWrapperDiagnostics:
    """Verify receive_wrapper logs ASGI messages correctly."""

    @pytest.mark.asyncio
    async def test_post_body_logged(self, caplog: Any) -> None:
        """POST body receive should emit a DEBUG log with body_len."""
        messages: list[Message] = [
            {"type": "http.request", "body": b"code=ABC123", "more_body": False},
        ]
        app = _make_app_that_reads_body()
        mw = _DebugLoggingMiddleware(app, debug_enabled=True)

        with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
            await mw(_make_scope(), _make_receive(messages), _noop_send)

        receive_logs = [r for r in caplog.records if "RECEIVE" in r.message]
        assert len(receive_logs) == 1
        assert "body_len=11" in receive_logs[0].message
        assert "more_body=False" in receive_logs[0].message

    @pytest.mark.asyncio
    async def test_disconnect_logged_as_warning(self, caplog: Any) -> None:
        """http.disconnect receive should emit a WARNING log."""
        messages: list[Message] = [
            {"type": "http.disconnect"},
        ]

        # App that reads once then returns
        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            """Read one message and return."""
            await receive()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = _DebugLoggingMiddleware(app, debug_enabled=True)

        with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
            await mw(_make_scope(), _make_receive(messages), _noop_send)

        warn_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "http.disconnect" in r.message
        ]
        assert len(warn_logs) == 1
        assert "client closed connection" in warn_logs[0].message

    @pytest.mark.asyncio
    async def test_get_request_no_receive_wrapper(self, caplog: Any) -> None:
        """GET requests should NOT use receive_wrapper."""
        called: list[str] = []

        async def inner_receive() -> Message:
            """Track calls and return disconnect."""
            called.append("receive")
            return {"type": "http.disconnect"}

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            """Just send a response."""
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = _DebugLoggingMiddleware(app, debug_enabled=True)

        with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
            await mw(
                _make_scope(method="GET"),
                inner_receive,
                _noop_send,
            )

        receive_logs = [r for r in caplog.records if "RECEIVE" in r.message]
        assert len(receive_logs) == 0

    @pytest.mark.asyncio
    async def test_debug_disabled_no_receive_wrapper(self, caplog: Any) -> None:
        """When debug is disabled, no receive logging occurs."""
        messages: list[Message] = [
            {"type": "http.request", "body": b"code=ABC", "more_body": False},
        ]
        app = _make_app_that_reads_body()
        mw = _DebugLoggingMiddleware(app, debug_enabled=False)

        with caplog.at_level(logging.DEBUG, logger="captive_portal.guest"):
            await mw(_make_scope(), _make_receive(messages), _noop_send)

        receive_logs = [r for r in caplog.records if "RECEIVE" in r.message]
        assert len(receive_logs) == 0


class TestExceptionDiagnostics:
    """Verify exception handlers log appropriately."""

    @pytest.mark.asyncio
    async def test_client_disconnect_logged(self, caplog: Any) -> None:
        """ClientDisconnect should log WARNING and re-raise."""
        mw = _DebugLoggingMiddleware(_make_disconnect_app(), debug_enabled=True)

        with (
            caplog.at_level(logging.DEBUG, logger="captive_portal.guest"),
            pytest.raises(ClientDisconnect),
        ):
            await mw(
                _make_scope(),
                _make_receive([]),
                _noop_send,
            )

        warn_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "CLIENT_DISCONNECT" in r.message
        ]
        assert len(warn_logs) == 1

    @pytest.mark.asyncio
    async def test_cancelled_error_logged(self, caplog: Any) -> None:
        """CancelledError should log WARNING and re-raise."""
        mw = _DebugLoggingMiddleware(_make_cancelled_app(), debug_enabled=True)

        with (
            caplog.at_level(logging.DEBUG, logger="captive_portal.guest"),
            pytest.raises(asyncio.CancelledError),
        ):
            await mw(
                _make_scope(),
                _make_receive([]),
                _noop_send,
            )

        warn_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "REQUEST_CANCELLED" in r.message
        ]
        assert len(warn_logs) == 1

    @pytest.mark.asyncio
    async def test_unhandled_error_logged(self, caplog: Any) -> None:
        """Unhandled exceptions should log ERROR and re-raise."""
        mw = _DebugLoggingMiddleware(_make_error_app(), debug_enabled=True)

        with (
            caplog.at_level(logging.DEBUG, logger="captive_portal.guest"),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await mw(
                _make_scope(),
                _make_receive([]),
                _noop_send,
            )

        err_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.ERROR and "UNHANDLED_ERROR" in r.message
        ]
        assert len(err_logs) == 1
