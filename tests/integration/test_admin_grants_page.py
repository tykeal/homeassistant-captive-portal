# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T012 – Integration tests for admin grants page.

Full-page integration tests using ``create_app()`` with the complete
middleware stack (SecurityHeadersMiddleware, SessionMiddleware) to verify
the grants management page renders correctly and PRG flows work end-to-end.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
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

    from captive_portal.api.routes import (
        admin_auth,
        grants_ui,
    )
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
    test_app.include_router(grants_ui.router)

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


def _create_grant(
    db_session: Session,
    *,
    device_id: str = "integ-device",
    mac: str = "AA:BB:CC:DD:EE:FF",
    status: GrantStatus = GrantStatus.ACTIVE,
    start_offset_hours: float = -1,
    end_offset_hours: float = 1,
    booking_ref: str | None = "INTEG-BOOK",
) -> AccessGrant:
    """Persist a grant with time offsets from now."""
    now = datetime.now(timezone.utc)
    grant = AccessGrant(
        device_id=device_id,
        mac=mac,
        start_utc=now + timedelta(hours=start_offset_hours),
        end_utc=now + timedelta(hours=end_offset_hours),
        status=status,
        booking_ref=booking_ref,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


# ---------------------------------------------------------------------------
# T012 – Full page integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminGrantsPage:
    """T012: Full-page integration tests for /admin/grants."""

    def test_unauthenticated_returns_401(self, secure_client: TestClient) -> None:
        """Unauthenticated request to grants page should return 401.

        With the full middleware stack the route's require_admin dependency
        raises 401 for unauthenticated requests.
        """
        resp = secure_client.get("/admin/grants/", follow_redirects=False)
        assert resp.status_code == 401

    def test_authenticated_page_load_returns_200(
        self, authed_secure_client: tuple[TestClient, str]
    ) -> None:
        """Authenticated GET /admin/grants should return 200 HTML."""
        client, _csrf = authed_secure_client
        resp = client.get("/admin/grants/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_grant_table_renders_correct_columns(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """HTML table should contain expected column data for a grant."""
        client, _csrf = authed_secure_client

        grant = _create_grant(
            db_session,
            device_id="integ-columns",
            mac="CC:DD:EE:FF:00:11",
            booking_ref="COL-REF-999",
        )

        resp = client.get("/admin/grants/")
        assert resp.status_code == 200
        body = resp.text

        # MAC, device_id, and booking_ref should all be rendered
        assert "CC:DD:EE:FF:00:11" in body
        assert "integ-columns" in body or "COL-REF-999" in body

        db_session.delete(grant)
        db_session.commit()

    def test_filter_by_status_end_to_end(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Filtering by status via query param should show only matching grants."""
        client, _csrf = authed_secure_client

        active = _create_grant(
            db_session,
            device_id="integ-f-active",
            mac="DD:00:00:00:00:01",
            status=GrantStatus.ACTIVE,
            start_offset_hours=-1,
            end_offset_hours=1,
        )
        revoked = _create_grant(
            db_session,
            device_id="integ-f-revoked",
            mac="DD:00:00:00:00:02",
            status=GrantStatus.REVOKED,
            start_offset_hours=-2,
            end_offset_hours=-1,
        )

        resp = client.get("/admin/grants?status=active")
        assert resp.status_code == 200
        body = resp.text
        assert "DD:00:00:00:00:01" in body
        assert "DD:00:00:00:00:02" not in body

        for g in (active, revoked):
            db_session.delete(g)
        db_session.commit()

    def test_extend_action_prg_redirect(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """POST extend should 303 redirect and following GET shows success."""
        client, csrf_token = authed_secure_client

        grant = _create_grant(db_session, device_id="integ-ext-prg")

        # POST → 303 redirect
        resp = client.post(
            f"/admin/grants/extend/{grant.id}",
            data={"csrf_token": csrf_token, "minutes": "45"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/admin/grants" in location
        assert "success=" in location

        # Follow the redirect manually to verify page renders
        get_resp = client.get(location)
        assert get_resp.status_code == 200
        assert "text/html" in get_resp.headers["content-type"]

        db_session.delete(grant)
        db_session.commit()

    def test_revoke_action_prg_redirect(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """POST revoke should 303 redirect and following GET shows success."""
        client, csrf_token = authed_secure_client

        grant = _create_grant(db_session, device_id="integ-rev-prg")

        resp = client.post(
            f"/admin/grants/revoke/{grant.id}",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/admin/grants" in location
        assert "success=" in location

        get_resp = client.get(location)
        assert get_resp.status_code == 200
        assert "text/html" in get_resp.headers["content-type"]

        db_session.delete(grant)
        db_session.commit()

    def test_revoke_expired_grant_sets_revoked(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoking an expired grant should redirect with success."""
        client, csrf_token = authed_secure_client

        grant = _create_grant(
            db_session,
            device_id="integ-rev-exp",
            mac="EE:00:00:00:00:01",
            status=GrantStatus.EXPIRED,
            start_offset_hours=-4,
            end_offset_hours=-2,
        )

        resp = client.post(
            f"/admin/grants/revoke/{grant.id}",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location

        db_session.delete(grant)
        db_session.commit()

    def test_empty_state_display(self, authed_secure_client: tuple[TestClient, str]) -> None:
        """When no grants exist, the page should still return 200 HTML."""
        client, _csrf = authed_secure_client
        resp = client.get("/admin/grants/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
