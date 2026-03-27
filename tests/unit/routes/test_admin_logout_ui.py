# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for admin logout UI route (T027).

Tests the admin_logout_ui route module which provides:
- POST /admin/logout — CSRF-exempt logout handler

The logout endpoint:
- Does NOT require ``require_admin`` (no auth dependency)
- Deletes the session from the in-memory store and clears the cookie
- Always redirects 303 to ``{root_path}/admin/login``
- Behaves as a graceful no-op when no session exists

These are TDD tests written before implementation.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser
from captive_portal.persistence.database import get_session
from captive_portal.security.password_hashing import hash_password
from captive_portal.security.session_middleware import (
    SessionConfig,
    SessionMiddleware,
    SessionStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def logout_app(db_engine: Engine) -> FastAPI:
    """App with logout UI and auth routes for unit testing."""
    from captive_portal.api.routes import admin_auth, admin_logout_ui

    test_app = FastAPI()
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)
    test_app.include_router(admin_logout_ui.router)
    test_app.include_router(admin_auth.router)

    def get_test_session() -> Generator[Session, None, None]:
        """Return a fake admin session for testing."""
        with Session(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = get_test_session
    return test_app


@pytest.fixture
def logout_client(logout_app: FastAPI) -> TestClient:
    """TestClient wired to the logout UI app."""
    return TestClient(logout_app)


@pytest.fixture
def admin_user(db_session: Session) -> Generator[Any, None, None]:
    """Create a test admin user."""
    admin = AdminUser(
        username="testadmin",
        password_hash=hash_password("SecureP@ss123"),
        email="testadmin@example.com",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    yield admin
    db_session.delete(admin)
    db_session.commit()


@pytest.fixture
def authenticated_client(logout_client: TestClient, admin_user: Any) -> tuple[TestClient, str]:
    """Returns (client, csrf_token) after login."""
    resp = logout_client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    logout_client.cookies.set("csrftoken", csrf_token)
    return logout_client, csrf_token


# ---------------------------------------------------------------------------
# T027 – POST /admin/logout
# ---------------------------------------------------------------------------


class TestLogoutRedirect:
    """T027: Authenticated logout redirects to login page."""

    def test_authenticated_logout_returns_303_redirect(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """POST /admin/logout with a valid session should return 303
        redirect to /admin/login."""
        client, _csrf = authenticated_client
        resp = client.post("/admin/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/admin/login")


class TestLogoutSessionDestroyed:
    """T027: Session is removed from store after logout."""

    def test_session_deleted_from_store(
        self,
        authenticated_client: tuple[TestClient, str],
        logout_app: FastAPI,
    ) -> None:
        """After POST /admin/logout the session_store should no longer
        contain the session that was active before logout."""
        client, _csrf = authenticated_client
        session_store: SessionStore = logout_app.state.session_store

        # Verify that a session exists before logout
        assert len(session_store._sessions) == 1
        session_id = next(iter(session_store._sessions))

        client.post("/admin/logout", follow_redirects=False)

        # Session should be gone
        assert session_store.get(session_id) is None
        assert len(session_store._sessions) == 0


class TestLogoutCookieCleared:
    """T027: Session cookie is cleared on logout."""

    def test_cookie_cleared_in_response(self, authenticated_client: tuple[TestClient, str]) -> None:
        """POST /admin/logout should set the session cookie with
        Max-Age=0 (or equivalent deletion) in the Set-Cookie header."""
        client, _csrf = authenticated_client
        resp = client.post("/admin/logout", follow_redirects=False)

        set_cookie = resp.headers.get("set-cookie", "")
        # Cookie deletion is indicated by max-age=0 or an expiry in the past
        cookie_lower = set_cookie.lower()
        assert "session_id" in cookie_lower
        assert "max-age=0" in cookie_lower or "expires=" in cookie_lower


class TestLogoutUnauthenticated:
    """T027: Logout with no session is a graceful no-op."""

    def test_no_session_still_redirects_303(self, logout_client: TestClient) -> None:
        """POST /admin/logout without any session should still return
        303 redirect to /admin/login (no error)."""
        resp = logout_client.post("/admin/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/admin/login")

    def test_no_session_does_not_raise(self, logout_client: TestClient) -> None:
        """POST /admin/logout without a session must not produce 4xx/5xx."""
        resp = logout_client.post("/admin/logout", follow_redirects=False)
        assert resp.status_code < 400


class TestLogoutCSRFExempt:
    """T027: POST /admin/logout works without CSRF token."""

    def test_post_without_csrf_token_succeeds(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """The logout route should be CSRF-exempt: a POST without
        a CSRF token header or cookie should still succeed."""
        client, _csrf = authenticated_client

        # Clear any CSRF cookies to prove exemption
        client.cookies.delete("csrftoken")

        resp = client.post(
            "/admin/logout",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/admin/login")
