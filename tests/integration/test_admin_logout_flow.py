# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T028 – Integration tests for the full admin logout flow.

Full-flow integration tests using a test app with the complete
middleware stack (SecurityHeadersMiddleware, SessionMiddleware) to verify
that logout correctly destroys the session, clears cookies, adds
security/cache-control headers, and works without JavaScript.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser
from captive_portal.security.password_hashing import hash_password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def secure_client(db_engine: Engine) -> TestClient:
    """Client backed by a test app with full middleware stack."""
    from fastapi import FastAPI
    from sqlmodel import Session as SqlSession

    from captive_portal.api.routes import admin_auth, admin_logout_ui, dashboard_ui
    from captive_portal.persistence.database import get_session
    from captive_portal.security.session_middleware import (
        SessionConfig,
        SessionMiddleware,
        SessionStore,
    )
    from captive_portal.web.middleware.security_headers import SecurityHeadersMiddleware

    test_app = FastAPI()
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store
    test_app.add_middleware(SecurityHeadersMiddleware)
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)
    test_app.include_router(admin_auth.router)
    test_app.include_router(admin_logout_ui.router)
    test_app.include_router(dashboard_ui.router)

    def get_test_session() -> Generator[Any, None, None]:
        """Return a fake admin session for testing."""
        with SqlSession(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = get_test_session
    return TestClient(test_app)


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
def authed_secure_client(secure_client: TestClient, admin_user: Any) -> tuple[TestClient, str]:
    """Authenticated secure_client returning (client, csrf_token)."""
    resp = secure_client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    secure_client.cookies.set("csrftoken", csrf_token)
    return secure_client, csrf_token


# ---------------------------------------------------------------------------
# T028 – Full logout flow integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminLogoutFlow:
    """T028: Full-flow integration tests for admin logout."""

    def test_logout_redirects_to_login_page(
        self, authed_secure_client: tuple[TestClient, str]
    ) -> None:
        """POST /admin/logout should 303 redirect to /admin/login."""
        client, _csrf = authed_secure_client
        resp = client.post("/admin/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/admin/login")

    def test_post_logout_admin_access_returns_401(
        self, authed_secure_client: tuple[TestClient, str]
    ) -> None:
        """After logout, accessing a protected admin page should return
        401 because the session has been destroyed."""
        client, _csrf = authed_secure_client

        # Verify dashboard is accessible before logout
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200

        # Perform logout
        client.post("/admin/logout", follow_redirects=False)

        # Dashboard should now be 401 (session gone)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 401

    def test_logout_response_includes_cache_control_headers(
        self, authed_secure_client: tuple[TestClient, str]
    ) -> None:
        """Logout response on /admin/* should include cache-control
        headers injected by SecurityHeadersMiddleware."""
        client, _csrf = authed_secure_client
        resp = client.post("/admin/logout", follow_redirects=False)

        cache_control = resp.headers.get("cache-control", "")
        assert "no-store" in cache_control or "no-cache" in cache_control

    def test_logout_works_without_js_no_form_data(
        self, authed_secure_client: tuple[TestClient, str]
    ) -> None:
        """The logout POST must work without JavaScript — a plain HTML
        form with no extra form data should succeed and redirect."""
        client, _csrf = authed_secure_client

        # Simulate a plain HTML form POST (no body, no CSRF, no JS)
        resp = client.post(
            "/admin/logout",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/admin/login")
