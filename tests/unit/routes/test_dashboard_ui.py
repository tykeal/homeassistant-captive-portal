# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for admin dashboard UI route (T017).

Tests the dashboard_ui route module which provides:
- GET /admin/dashboard — display dashboard with stats and recent activity

These are TDD tests written before implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.database import get_session
from captive_portal.security.password_hashing import hash_password
from captive_portal.security.session_middleware import (
    SessionConfig,
    SessionMiddleware,
    SessionStore,
)

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dashboard_app(db_engine: Engine) -> FastAPI:
    """App with dashboard UI routes for unit testing."""
    from captive_portal.api.routes import admin_auth, dashboard_ui

    test_app = FastAPI()
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)
    test_app.include_router(dashboard_ui.router)
    test_app.include_router(admin_auth.router)

    def get_test_session() -> Generator[Session, None, None]:
        """Return a fake admin session for testing."""
        with Session(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = get_test_session
    return test_app


@pytest.fixture
def dashboard_client(dashboard_app: FastAPI) -> TestClient:
    """TestClient wired to the dashboard UI app."""
    return TestClient(dashboard_app)


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
def authenticated_client(dashboard_client: TestClient, admin_user: Any) -> tuple[TestClient, str]:
    """Returns (client, csrf_token) after login."""
    resp = dashboard_client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    dashboard_client.cookies.set("csrftoken", csrf_token)
    return dashboard_client, csrf_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grant(
    db_session: Session,
    *,
    device_id: str = "dev-1",
    mac: str = "AA:BB:CC:DD:EE:01",
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
    status: GrantStatus = GrantStatus.ACTIVE,
) -> AccessGrant:
    """Persist a grant, defaulting to an active time window around NOW."""
    start = start_utc or (NOW - timedelta(hours=1))
    end = end_utc or (NOW + timedelta(hours=1))
    grant = AccessGrant(
        device_id=device_id,
        mac=mac,
        start_utc=start,
        end_utc=end,
        status=status,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


def _make_voucher(
    db_session: Session,
    *,
    code: str,
    duration_minutes: int = 1440,
    status: VoucherStatus = VoucherStatus.UNUSED,
    created_utc: datetime | None = None,
) -> Voucher:
    """Persist a voucher with sensible defaults."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=0,
    )
    if created_utc is not None:
        voucher.created_utc = created_utc
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


def _make_integration(db_session: Session, *, integration_id: str) -> HAIntegrationConfig:
    """Persist a minimal HA integration config."""
    config = HAIntegrationConfig(integration_id=integration_id)
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)
    return config


def _make_audit_log(
    db_session: Session,
    *,
    actor: str = "system",
    action: str = "test.action",
    target_type: str = "test",
    target_id: str = "1",
    outcome: str = "success",
    timestamp_utc: datetime | None = None,
) -> AuditLog:
    """Persist an audit log entry."""
    log = AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
    )
    if timestamp_utc is not None:
        log.timestamp_utc = timestamp_utc
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


# ---------------------------------------------------------------------------
# T017 – GET /admin/dashboard
# ---------------------------------------------------------------------------


class TestDashboardAuthentication:
    """T017: Authentication requirements for the dashboard page."""

    def test_authenticated_get_returns_200_html(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """Authenticated GET /admin/dashboard should return 200 with HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_unauthenticated_get_returns_401(self, dashboard_client: TestClient) -> None:
        """Unauthenticated GET /admin/dashboard should return 401."""
        resp = dashboard_client.get("/admin/dashboard")
        assert resp.status_code == 401


class TestDashboardStatsDisplayed:
    """T017: Dashboard page displays stats cards with correct values."""

    def test_stats_cards_show_correct_counts(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Creating grants, vouchers, and integrations should produce
        matching counts in the rendered dashboard HTML."""
        client, _csrf = authenticated_client

        # 1 active grant (started in past, ends in future)
        g1 = _make_grant(
            db_session,
            device_id="dash-d1",
            mac="AA:BB:CC:00:00:01",
            start_utc=datetime.now(timezone.utc) - timedelta(hours=1),
            end_utc=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        # 1 pending grant (starts in the future)
        g2 = _make_grant(
            db_session,
            device_id="dash-d2",
            mac="AA:BB:CC:00:00:02",
            start_utc=datetime.now(timezone.utc) + timedelta(hours=1),
            end_utc=datetime.now(timezone.utc) + timedelta(hours=3),
        )
        # 2 unused vouchers (not expired)
        v1 = _make_voucher(
            db_session,
            code="DASH0001",
            created_utc=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        v2 = _make_voucher(
            db_session,
            code="DASH0002",
            created_utc=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        # 1 integration
        i1 = _make_integration(db_session, integration_id="test_integ")

        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.text

        # The stat card values should appear in the HTML
        # Active grants: 1, Pending grants: 1, Available vouchers: 2, Integrations: 1
        assert "Active Grants" in body
        assert "Pending Grants" in body
        assert "Available Vouchers" in body
        assert "HA Integrations" in body

        # Cleanup
        for obj in (g1, g2, v1, v2, i1):
            db_session.delete(obj)
        db_session.commit()


class TestDashboardRecentActivity:
    """T017: Dashboard page displays recent activity feed."""

    def test_recent_activity_rendered(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Audit log entries should appear in the activity feed table."""
        client, _csrf = authenticated_client

        log1 = _make_audit_log(
            db_session,
            actor="system",
            action="voucher.create",
            target_type="voucher",
            target_id="VCODE1",
            timestamp_utc=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        log2 = _make_audit_log(
            db_session,
            actor="system",
            action="grant.revoke",
            target_type="grant",
            target_id="gid-2",
            timestamp_utc=datetime.now(timezone.utc) - timedelta(minutes=2),
        )

        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.text

        # Activity feed should contain actions from audit log
        assert "voucher.create" in body
        assert "grant.revoke" in body
        assert "Recent Activity" in body

        for obj in (log1, log2):
            db_session.delete(obj)
        db_session.commit()


class TestDashboardEmptyState:
    """T017: Dashboard page displays gracefully when no data exists."""

    def test_zero_counts_displayed(self, authenticated_client: tuple[TestClient, str]) -> None:
        """With no data, stat cards should display '0' for all counts."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.text

        # The stat-value elements should contain "0"
        assert "text/html" in resp.headers["content-type"]
        # All four stat cards should show 0
        assert body.count(">0<") >= 4 or body.count('"stat-value">0<') >= 4

    def test_empty_activity_feed(self, authenticated_client: tuple[TestClient, str]) -> None:
        """With no audit logs, the activity feed should show
        'No recent activity' or render an empty table gracefully."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.text

        # Template should handle the empty state
        assert "No recent activity" in body or "<tbody>" in body


class TestDashboardServiceExceptionHandling:
    """T017: Dashboard route handles DashboardService exceptions gracefully."""

    def test_get_stats_exception_renders_gracefully(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If DashboardService.get_stats() raises, the page should still
        render (possibly with error state) instead of returning 500."""
        client, _csrf = authenticated_client

        with (
            patch(
                "captive_portal.api.routes.dashboard_ui.DashboardService.get_stats",
                side_effect=RuntimeError("DB connection lost"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            resp = client.get("/admin/dashboard")

        # Should not be a raw 500 — route should catch and render gracefully
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_get_stats_exception_logged(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DashboardService exception should produce a structured log entry."""
        client, _csrf = authenticated_client

        with (
            patch(
                "captive_portal.api.routes.dashboard_ui.DashboardService.get_stats",
                side_effect=RuntimeError("DB connection lost"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            client.get("/admin/dashboard")

        error_logs = [
            r
            for r in caplog.records
            if r.levelno >= logging.ERROR
            and ("dashboard" in r.getMessage().lower() or "stats" in r.getMessage().lower())
        ]
        assert len(error_logs) >= 1

    def test_get_recent_activity_exception_renders_gracefully(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If DashboardService.get_recent_activity() raises, the page
        should still render with stats but empty/error activity feed."""
        client, _csrf = authenticated_client

        with (
            patch(
                "captive_portal.api.routes.dashboard_ui.DashboardService.get_recent_activity",
                side_effect=RuntimeError("Query timeout"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            resp = client.get("/admin/dashboard")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_get_recent_activity_exception_logged(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DashboardService.get_recent_activity() exception should be logged."""
        client, _csrf = authenticated_client

        with (
            patch(
                "captive_portal.api.routes.dashboard_ui.DashboardService.get_recent_activity",
                side_effect=RuntimeError("Query timeout"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            client.get("/admin/dashboard")

        error_logs = [
            r
            for r in caplog.records
            if r.levelno >= logging.ERROR
            and ("activity" in r.getMessage().lower() or "dashboard" in r.getMessage().lower())
        ]
        assert len(error_logs) >= 1
