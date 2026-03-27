# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for admin grants UI routes (T009, T010, T011).

Tests the grants_ui route module which provides:
- GET /admin/grants — list grants with status filter (T009)
- POST /admin/grants/extend/{grant_id} — extend grant duration (T010)
- POST /admin/grants/revoke/{grant_id} — revoke grant (T011)

These are TDD tests written before implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
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
def grants_app(db_engine: Engine) -> FastAPI:
    """App with grants UI routes for unit testing."""
    from captive_portal.api.routes import admin_auth, grants_ui

    test_app = FastAPI()
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)
    test_app.include_router(grants_ui.router)
    test_app.include_router(admin_auth.router)

    def get_test_session() -> Generator[Session, None, None]:
        """Return a fake admin session for testing."""
        with Session(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = get_test_session
    return test_app


@pytest.fixture
def grants_client(grants_app: FastAPI) -> TestClient:
    """TestClient wired to the grants UI app."""
    return TestClient(grants_app)


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
def authenticated_client(grants_client: TestClient, admin_user: Any) -> tuple[TestClient, str]:
    """Returns (client, csrf_token) after login."""
    resp = grants_client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    grants_client.cookies.set("csrftoken", csrf_token)
    return grants_client, csrf_token


def _make_grant(
    db_session: Session,
    *,
    device_id: str = "test-device",
    mac: str = "AA:BB:CC:DD:EE:FF",
    status: GrantStatus = GrantStatus.ACTIVE,
    start_offset_hours: float = -1,
    end_offset_hours: float = 1,
    booking_ref: str | None = "BOOK-001",
) -> AccessGrant:
    """Helper to create and persist a grant with time offsets from now."""
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
# T009 – GET /admin/grants
# ---------------------------------------------------------------------------


class TestGetGrantsPage:
    """T009: GET /admin/grants — list grants with status filter."""

    def test_authenticated_get_returns_200_html(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """Authenticated GET should return 200 with HTML content."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/grants")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_unauthenticated_get_returns_401(self, grants_client: TestClient) -> None:
        """Unauthenticated GET should return 401."""
        resp = grants_client.get("/admin/grants")
        assert resp.status_code == 401

    def test_grants_listed_with_status_recomputation(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Grants should be listed with status recomputed at render time.

        An active grant (start in past, end in future), an expired grant
        (start and end in past), and a pending grant (start in future)
        should all appear with correct computed status.
        """
        client, _csrf = authenticated_client

        active = _make_grant(
            db_session,
            device_id="dev-active",
            mac="AA:BB:CC:00:00:01",
            status=GrantStatus.ACTIVE,
            start_offset_hours=-1,
            end_offset_hours=1,
        )
        expired = _make_grant(
            db_session,
            device_id="dev-expired",
            mac="AA:BB:CC:00:00:02",
            status=GrantStatus.ACTIVE,
            start_offset_hours=-3,
            end_offset_hours=-1,
        )
        pending = _make_grant(
            db_session,
            device_id="dev-pending",
            mac="AA:BB:CC:00:00:03",
            status=GrantStatus.PENDING,
            start_offset_hours=1,
            end_offset_hours=3,
        )

        resp = client.get("/admin/grants")
        assert resp.status_code == 200
        body = resp.text

        # All three MACs should appear in the HTML
        assert "AA:BB:CC:00:00:01" in body
        assert "AA:BB:CC:00:00:02" in body
        assert "AA:BB:CC:00:00:03" in body

        # Cleanup
        for g in (active, expired, pending):
            db_session.delete(g)
        db_session.commit()

    def test_status_filter_query_param(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """GET with ?status=active should filter to active grants only."""
        client, _csrf = authenticated_client

        active = _make_grant(
            db_session,
            device_id="dev-filter-active",
            mac="FF:00:00:00:00:01",
            status=GrantStatus.ACTIVE,
            start_offset_hours=-1,
            end_offset_hours=1,
        )
        revoked = _make_grant(
            db_session,
            device_id="dev-filter-revoked",
            mac="FF:00:00:00:00:02",
            status=GrantStatus.REVOKED,
            start_offset_hours=-2,
            end_offset_hours=-1,
        )

        resp = client.get("/admin/grants?status=active")
        assert resp.status_code == 200
        body = resp.text

        # Active grant MAC should be visible
        assert "FF:00:00:00:00:01" in body
        # Revoked grant MAC should not be visible
        assert "FF:00:00:00:00:02" not in body

        for g in (active, revoked):
            db_session.delete(g)
        db_session.commit()

    def test_empty_state_no_grants(self, authenticated_client: tuple[TestClient, str]) -> None:
        """When no grants exist, page should still return 200 HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/grants")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_success_message_displayed(self, authenticated_client: tuple[TestClient, str]) -> None:
        """Success query param should be reflected in the rendered HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/grants?success=Grant+extended+by+60+minutes")
        assert resp.status_code == 200
        assert "Grant extended by 60 minutes" in resp.text

    def test_error_message_displayed(self, authenticated_client: tuple[TestClient, str]) -> None:
        """Error query param should be reflected in the rendered HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/grants?error=Grant+not+found")
        assert resp.status_code == 200
        assert "Grant not found" in resp.text


# ---------------------------------------------------------------------------
# T010 – POST /admin/grants/extend/{grant_id}
# ---------------------------------------------------------------------------


class TestExtendGrant:
    """T010: POST /admin/grants/extend/{grant_id} — extend grant duration."""

    def test_successful_extend(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Valid extend request should 303 redirect with success message."""
        client, csrf_token = authenticated_client

        grant = _make_grant(db_session, device_id="dev-ext-ok")
        resp = client.post(
            f"/admin/grants/extend/{grant.id}",
            data={"csrf_token": csrf_token, "minutes": "60"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/admin/grants" in location
        assert "success=" in location
        assert "60" in location

        db_session.delete(grant)
        db_session.commit()

    def test_extend_expired_grant_succeeds(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Extending an expired grant should reactivate it and redirect with success."""
        client, csrf_token = authenticated_client

        grant = _make_grant(
            db_session,
            device_id="dev-ext-expired",
            mac="AA:BB:CC:00:EE:01",
            status=GrantStatus.EXPIRED,
            start_offset_hours=-3,
            end_offset_hours=-1,
        )
        resp = client.post(
            f"/admin/grants/extend/{grant.id}",
            data={"csrf_token": csrf_token, "minutes": "120"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location

        db_session.delete(grant)
        db_session.commit()

    def test_extend_not_found(self, authenticated_client: tuple[TestClient, str]) -> None:
        """Extending non-existent grant should redirect with error."""
        client, csrf_token = authenticated_client
        fake_id = uuid4()

        resp = client.post(
            f"/admin/grants/extend/{fake_id}",
            data={"csrf_token": csrf_token, "minutes": "30"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "not+found" in location.lower() or "not found" in location.lower()

    def test_extend_revoked_grant(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Extending a revoked grant should redirect with error."""
        client, csrf_token = authenticated_client

        grant = _make_grant(
            db_session,
            device_id="dev-ext-revoked",
            mac="AA:BB:CC:00:EE:02",
            status=GrantStatus.REVOKED,
            start_offset_hours=-2,
            end_offset_hours=-1,
        )
        resp = client.post(
            f"/admin/grants/extend/{grant.id}",
            data={"csrf_token": csrf_token, "minutes": "30"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "revoked" in location.lower()

        db_session.delete(grant)
        db_session.commit()

    def test_extend_invalid_csrf(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Invalid CSRF token should redirect with error."""
        client, _csrf = authenticated_client

        grant = _make_grant(db_session, device_id="dev-ext-csrf")
        resp = client.post(
            f"/admin/grants/extend/{grant.id}",
            data={"csrf_token": "wrong-token-value", "minutes": "30"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "csrf" in location.lower() or "CSRF" in location

        db_session.delete(grant)
        db_session.commit()

    @pytest.mark.parametrize(
        "minutes_value,desc",
        [
            ("0", "zero"),
            ("-5", "negative"),
            ("1441", "exceeds max"),
            ("abc", "non-numeric"),
        ],
    )
    def test_extend_invalid_minutes(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
        minutes_value: str,
        desc: str,
    ) -> None:
        """Invalid minutes values should redirect with error."""
        client, csrf_token = authenticated_client

        grant = _make_grant(db_session, device_id=f"dev-ext-bad-{desc}", mac="AA:BB:CC:DD:00:09")
        resp = client.post(
            f"/admin/grants/extend/{grant.id}",
            data={"csrf_token": csrf_token, "minutes": minutes_value},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "minutes" in location.lower() or "Minutes" in location

        db_session.delete(grant)
        db_session.commit()

    def test_extend_not_found_logging(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """GrantNotFoundError on extend should produce structured log."""
        client, csrf_token = authenticated_client
        fake_id = uuid4()

        with caplog.at_level(logging.WARNING):
            client.post(
                f"/admin/grants/extend/{fake_id}",
                data={"csrf_token": csrf_token, "minutes": "30"},
                follow_redirects=False,
            )

        # At least one log record should reference the grant id
        grant_logs = [r for r in caplog.records if str(fake_id) in r.getMessage()]
        assert len(grant_logs) >= 1

    def test_extend_revoked_logging(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """GrantOperationError on extend should produce structured log."""
        client, csrf_token = authenticated_client

        grant = _make_grant(
            db_session,
            device_id="dev-ext-revoked-log",
            mac="AA:BB:CC:DD:00:0A",
            status=GrantStatus.REVOKED,
        )
        with caplog.at_level(logging.WARNING):
            client.post(
                f"/admin/grants/extend/{grant.id}",
                data={"csrf_token": csrf_token, "minutes": "30"},
                follow_redirects=False,
            )

        grant_logs = [r for r in caplog.records if str(grant.id) in r.getMessage()]
        assert len(grant_logs) >= 1

        db_session.delete(grant)
        db_session.commit()


# ---------------------------------------------------------------------------
# T011 – POST /admin/grants/revoke/{grant_id}
# ---------------------------------------------------------------------------


class TestRevokeGrant:
    """T011: POST /admin/grants/revoke/{grant_id} — revoke grant."""

    def test_successful_revoke(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Valid revoke request should 303 redirect with success message."""
        client, csrf_token = authenticated_client

        grant = _make_grant(db_session, device_id="dev-rev-ok")
        resp = client.post(
            f"/admin/grants/revoke/{grant.id}",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/admin/grants" in location
        assert "success=" in location
        assert "revoked" in location.lower() or "Revoked" in location

        db_session.delete(grant)
        db_session.commit()

    def test_revoke_already_revoked_idempotent(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoking an already-revoked grant should still succeed (idempotent)."""
        client, csrf_token = authenticated_client

        grant = _make_grant(
            db_session,
            device_id="dev-rev-idem",
            mac="AA:BB:CC:DD:00:0B",
            status=GrantStatus.REVOKED,
            start_offset_hours=-2,
            end_offset_hours=-1,
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

    def test_revoke_expired_grant(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoking an expired grant should succeed with redirect."""
        client, csrf_token = authenticated_client

        grant = _make_grant(
            db_session,
            device_id="dev-rev-expired",
            mac="AA:BB:CC:DD:00:0C",
            status=GrantStatus.EXPIRED,
            start_offset_hours=-3,
            end_offset_hours=-1,
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

    def test_revoke_not_found(self, authenticated_client: tuple[TestClient, str]) -> None:
        """Revoking non-existent grant should redirect with error."""
        client, csrf_token = authenticated_client
        fake_id = uuid4()

        resp = client.post(
            f"/admin/grants/revoke/{fake_id}",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "not+found" in location.lower() or "not found" in location.lower()

    def test_revoke_invalid_csrf(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Invalid CSRF token should redirect with error."""
        client, _csrf = authenticated_client

        grant = _make_grant(db_session, device_id="dev-rev-csrf")
        resp = client.post(
            f"/admin/grants/revoke/{grant.id}",
            data={"csrf_token": "wrong-token-value"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "csrf" in location.lower() or "CSRF" in location

        db_session.delete(grant)
        db_session.commit()
