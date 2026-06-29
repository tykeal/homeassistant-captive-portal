# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Edge-case coverage for security helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from captive_portal.security import password_hashing
from captive_portal.security.hmac_csrf import HMACCSRFProtection, _parse_host_header
from captive_portal.security.password_hashing import hash_password
from captive_portal.security.rate_limiter import RateLimiter
from captive_portal.security.session_middleware import (
    SessionConfig,
    SessionData,
    SessionMiddleware,
    SessionStore,
    refresh_runtime_session_config,
)


def test_parse_host_header_handles_empty_and_bad_ports() -> None:
    """Host parsing tolerates empty, malformed IPv6, and bad ports."""
    assert _parse_host_header("   ") == ("", None)
    assert _parse_host_header("[::1") == ("[::1", None)
    assert _parse_host_header("[::1]:notaport") == ("::1", None)
    assert _parse_host_header("::1") == ("::1", None)
    assert _parse_host_header("portal.local:notaport") == ("portal.local:notaport", None)


@pytest.mark.asyncio
async def test_hmac_rejects_malformed_payload_and_timestamp() -> None:
    """Signed tokens with bad payloads are rejected after signature validation."""
    csrf = HMACCSRFProtection()

    malformed_payload = "onlynonce"
    malformed_token = _signed_token(csrf, malformed_payload)
    with pytest.raises(Exception, match="Malformed CSRF token payload"):
        await csrf.validate_token(_request_with_header(malformed_token))

    invalid_timestamp_payload = "nonce:not-an-int"
    invalid_timestamp_token = _signed_token(csrf, invalid_timestamp_payload)
    with pytest.raises(Exception, match="Invalid CSRF token timestamp"):
        await csrf.validate_token(_request_with_header(invalid_timestamp_token))


@pytest.mark.asyncio
async def test_hmac_origin_uses_structured_request_url() -> None:
    """Origin validation prefers request.url hostname and port when present."""
    csrf = HMACCSRFProtection()
    token = csrf.generate_token()
    request = _request_with_header(
        token,
        headers={"origin": "http://portal.local:8080", "host": "ignored.example"},
    )
    request.url.hostname = "portal.local"
    request.url.port = 8080

    await csrf.validate_token(request)


def _signed_token(csrf: HMACCSRFProtection, payload: str) -> str:
    """Build a base64 HMAC token for an arbitrary payload."""
    import base64
    import hashlib
    import hmac

    signature = hmac.new(
        csrf.config.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode()


def _request_with_header(token: str, headers: dict[str, str] | None = None) -> Any:
    """Create a request-like object carrying an HMAC CSRF header."""
    header_values = {"X-CSRF-Token": token}
    if headers is not None:
        header_values.update(headers)
    return SimpleNamespace(
        headers=header_values,
        method="POST",
        query_params={},
        url=SimpleNamespace(hostname=None, port=None),
    )


def test_hash_password_wraps_hasher_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """hash_password reports lower-level hasher failures as ValueError."""

    def fail_hash(_password: str) -> str:
        """Raise a synthetic hashing failure."""
        raise RuntimeError("argon unavailable")

    monkeypatch.setattr(password_hashing, "_ph", SimpleNamespace(hash=fail_hash))

    with pytest.raises(ValueError, match="Password hashing failed"):
        hash_password("secret")


def test_rate_limiter_retry_after_allows_empty_and_expired() -> None:
    """Retry-after returns None when no current attempt blocks the IP."""
    limiter = RateLimiter(max_attempts=1, window_seconds=1)
    assert limiter.get_retry_after_seconds("192.0.2.10") is None
    limiter._attempts["192.0.2.10"].append(datetime.now(timezone.utc) - timedelta(seconds=5))
    assert limiter.get_retry_after_seconds("192.0.2.10") is None


def test_refresh_runtime_session_config_creates_missing_config() -> None:
    """Refreshing app state creates a default config when one is absent."""
    state = SimpleNamespace()

    refreshed = refresh_runtime_session_config(state, idle_minutes=10, max_hours=2)

    assert isinstance(refreshed, SessionConfig)
    assert refreshed.idle_minutes == 10
    assert refreshed.max_hours == 2
    assert state.session_config is refreshed


def test_session_store_update_activity_missing_session() -> None:
    """Updating a missing session returns False."""
    store = SessionStore()
    assert store.update_activity("missing", SessionConfig()) is False


def test_session_middleware_create_and_delete_session_cookie() -> None:
    """Session middleware writes and clears cookies around store changes."""
    store = SessionStore()
    middleware = SessionMiddleware(
        _ok_app,
        config=SessionConfig(cookie_secure=False),
        store=store,
    )
    response = Response()
    admin_id = uuid4()

    session_id = middleware.create_session(
        response,
        admin_id,
        ip_address="192.0.2.20",
        user_agent="pytest",
    )

    assert store.get(session_id) is not None
    assert "session_id=" in response.headers["set-cookie"]

    delete_response = Response()
    assert middleware.delete_session(delete_response, session_id) is True
    assert store.get(session_id) is None
    assert "Max-Age=0" in delete_response.headers["set-cookie"]


def test_session_middleware_dispatch_handles_valid_session() -> None:
    """Dispatch attaches a valid admin session to request state."""
    app = FastAPI()
    store = SessionStore()
    config = SessionConfig(cookie_secure=False)
    admin_id = uuid4()
    session_id = store.create(admin_id, config)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str]:
        """Return session state populated by middleware."""
        return {"admin_id": str(request.state.admin_id)}

    app.add_middleware(SessionMiddleware, config=config, store=store)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/whoami")

    assert response.status_code == 200
    assert response.json() == {"admin_id": str(admin_id)}


async def _ok_app(scope: Any, receive: Any, send: Any) -> None:
    """No-op ASGI app for middleware construction."""
    del scope, receive, send


def _expired_session() -> SessionData:
    """Create an already expired session data object."""
    now = datetime.now(timezone.utc)
    return SessionData(
        admin_id=uuid4(),
        created_utc=now - timedelta(hours=2),
        last_activity_utc=now - timedelta(hours=2),
        expires_utc=now - timedelta(hours=1),
    )


def test_session_store_delete_missing_session() -> None:
    """Deleting a missing session returns False."""
    store = SessionStore()
    assert store.delete("missing") is False


def test_session_store_cleanup_removes_expired_session() -> None:
    """Session cleanup deletes sessions past their expiry."""
    store = SessionStore()
    store._sessions["expired"] = _expired_session()
    assert store.cleanup_expired(SessionConfig()) == 1
    assert store.get("expired") is None


@pytest.mark.asyncio
async def test_rbac_enforcer_uses_action_header_by_default() -> None:
    """RBAC middleware reads X-Action when no explicit action is supplied."""
    from starlette.requests import Request

    from captive_portal.middleware import rbac_enforcer

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"x-role", b"admin"),
            (b"x-action", b"admin.accounts.list"),
        ],
    }
    request = Request(scope)

    await rbac_enforcer(request)


def test_parse_host_header_handles_bracketed_ipv6_without_port() -> None:
    """Host parsing supports bracketed IPv6 addresses without ports."""
    assert _parse_host_header("[::1]") == ("::1", None)
