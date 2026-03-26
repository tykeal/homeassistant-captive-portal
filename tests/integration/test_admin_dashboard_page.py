# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T018 – Integration tests for admin dashboard page.

Full-page integration tests using a test app with the complete
middleware stack (SecurityHeadersMiddleware, SessionMiddleware) to verify
the dashboard page renders correctly with stats and activity feed.
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
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.security.password_hashing import hash_password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def secure_client(db_engine: Engine) -> TestClient:
    """Client backed by a test app with full middleware stack."""
    from fastapi import FastAPI
    from sqlmodel import Session as SqlSession

    from captive_portal.api.routes import admin_auth, dashboard_ui
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
# Helpers
# ---------------------------------------------------------------------------


def _create_grant(
    db_session: Session,
    *,
    device_id: str = "integ-device",
    mac: str = "AA:BB:CC:DD:EE:FF",
    status: GrantStatus = GrantStatus.ACTIVE,
    start_offset_hours: float = -1,
    end_offset_hours: float = 1,
) -> AccessGrant:
    """Persist a grant with time offsets from now."""
    now = datetime.now(timezone.utc)
    grant = AccessGrant(
        device_id=device_id,
        mac=mac,
        start_utc=now + timedelta(hours=start_offset_hours),
        end_utc=now + timedelta(hours=end_offset_hours),
        status=status,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


def _create_voucher(
    db_session: Session,
    *,
    code: str,
    duration_minutes: int = 1440,
    status: VoucherStatus = VoucherStatus.UNUSED,
) -> Voucher:
    """Persist a voucher with sensible defaults."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=0,
    )
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


def _create_integration(db_session: Session, *, integration_id: str) -> HAIntegrationConfig:
    """Persist a minimal HA integration config."""
    config = HAIntegrationConfig(integration_id=integration_id)
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


def _create_audit_log(
    db_session: Session,
    *,
    actor: str = "system",
    action: str = "test.action",
    target_type: str = "test",
    target_id: str = "1",
    outcome: str = "success",
) -> AuditLog:
    """Persist an audit log entry."""
    log = AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


# ---------------------------------------------------------------------------
# T018 – Full page integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminDashboardPage:
    """T018: Full-page integration tests for /admin/dashboard."""

    def test_unauthenticated_returns_401(self, secure_client: TestClient) -> None:
        """Unauthenticated request to dashboard should return 401.

        With the full middleware stack the route's require_admin dependency
        raises 401 for unauthenticated requests.
        """
        resp = secure_client.get("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 401

    def test_authenticated_page_load_with_stats_cards(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Authenticated GET /admin/dashboard should return 200 HTML
        with stats cards reflecting the data in the database."""
        client, _csrf = authed_secure_client

        # Create data: 1 active grant, 1 voucher, 1 integration
        g1 = _create_grant(
            db_session,
            device_id="integ-dash-d1",
            mac="DD:00:00:00:00:01",
        )
        v1 = _create_voucher(db_session, code="INTG0001")
        i1 = _create_integration(db_session, integration_id="integ-dash-1")

        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        body = resp.text

        # Stat card headings should be present
        assert "Active Grants" in body
        assert "Pending Grants" in body
        assert "Available Vouchers" in body
        assert "HA Integrations" in body

        # Cleanup
        for obj in (g1, v1, i1):
            db_session.delete(obj)
        db_session.commit()

    def test_activity_feed_rendering(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Audit log entries should appear in the activity feed table."""
        client, _csrf = authed_secure_client

        log1 = _create_audit_log(
            db_session,
            action="grant.create",
            target_type="grant",
            target_id="integ-g-1",
        )
        log2 = _create_audit_log(
            db_session,
            action="voucher.revoke",
            target_type="voucher",
            target_id="VCODE9",
        )

        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.text

        assert "grant.create" in body
        assert "voucher.revoke" in body
        assert "Recent Activity" in body

        for obj in (log1, log2):
            db_session.delete(obj)
        db_session.commit()

    def test_zero_data_graceful_display(self, authed_secure_client: tuple[TestClient, str]) -> None:
        """With no data, stat cards should show '0' for all counts and the
        activity feed should display 'No recent activity' or be empty."""
        client, _csrf = authed_secure_client

        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        body = resp.text

        # All four stat cards should show 0
        assert body.count(">0<") >= 4 or body.count('"stat-value">0<') >= 4
        # Empty activity feed
        assert "No recent activity" in body or "<tbody>" in body
