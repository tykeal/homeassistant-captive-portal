# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for runtime session middleware configuration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from starlette.types import Receive, Scope, Send

from captive_portal.security.session_middleware import (
    SessionConfig,
    SessionData,
    SessionMiddleware,
    SessionStore,
    refresh_runtime_session_config,
)


async def _noop_app(scope: Scope, receive: Receive, send: Send) -> None:
    """Provide a no-op ASGI app for middleware construction.

    Args:
        scope: ASGI connection scope.
        receive: ASGI receive callable.
        send: ASGI send callable.

    Returns:
        None.
    """
    del scope, receive, send


def test_session_store_uses_current_max_hours() -> None:
    """Session cleanup applies updated max_hours to existing sessions."""
    now = datetime.now(timezone.utc)
    store = SessionStore()
    store._sessions["existing"] = SessionData(
        admin_id=uuid4(),
        created_utc=now - timedelta(hours=2),
        last_activity_utc=now,
        expires_utc=now + timedelta(hours=6),
    )

    removed = store.cleanup_expired(SessionConfig(idle_minutes=30, max_hours=1))

    assert removed == 1
    assert store.get("existing") is None


def test_middleware_uses_current_max_hours() -> None:
    """Middleware expiry applies updated max_hours to existing sessions."""
    now = datetime.now(timezone.utc)
    middleware = SessionMiddleware(
        _noop_app,
        config=SessionConfig(idle_minutes=30, max_hours=1),
    )
    session = SessionData(
        admin_id=uuid4(),
        created_utc=now - timedelta(hours=2),
        last_activity_utc=now,
        expires_utc=now + timedelta(hours=6),
    )

    assert middleware._is_session_expired(session) is True


def test_middleware_preserves_stored_absolute_expiry() -> None:
    """Middleware does not revive sessions expired before a config increase."""
    now = datetime.now(timezone.utc)
    middleware = SessionMiddleware(
        _noop_app,
        config=SessionConfig(idle_minutes=30, max_hours=8),
    )
    session = SessionData(
        admin_id=uuid4(),
        created_utc=now - timedelta(hours=2),
        last_activity_utc=now,
        expires_utc=now - timedelta(minutes=1),
    )

    assert middleware._is_session_expired(session) is True


def test_refresh_caps_existing_session_expiry() -> None:
    """Runtime refresh removes sessions expired by a max_hours reduction."""
    now = datetime.now(timezone.utc)
    store = SessionStore()
    store._sessions["existing"] = SessionData(
        admin_id=uuid4(),
        created_utc=now - timedelta(hours=2),
        last_activity_utc=now,
        expires_utc=now + timedelta(hours=6),
    )
    state = SimpleNamespace(
        session_config=SessionConfig(idle_minutes=30, max_hours=8),
        session_store=store,
    )

    refresh_runtime_session_config(state, idle_minutes=30, max_hours=1)

    assert store.get("existing") is None
    assert state.session_config.max_hours == 1


def test_refresh_removes_sessions_idle_expired_before_increase() -> None:
    """Runtime refresh does not revive sessions idle-expired before increase."""
    now = datetime.now(timezone.utc)
    store = SessionStore()
    store._sessions["existing"] = SessionData(
        admin_id=uuid4(),
        created_utc=now - timedelta(hours=1),
        last_activity_utc=now - timedelta(minutes=45),
        expires_utc=now + timedelta(hours=7),
    )
    state = SimpleNamespace(
        session_config=SessionConfig(idle_minutes=30, max_hours=8),
        session_store=store,
    )

    refresh_runtime_session_config(state, idle_minutes=60, max_hours=8)

    assert store.get("existing") is None
    assert state.session_config.idle_minutes == 60
