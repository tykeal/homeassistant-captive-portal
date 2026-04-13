# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for admin manual purge UI flow.

T017: Tests for the purge preview/confirm two-step flow including
form validation, confirmation banner, success messages, N=0 behavior,
invalid input handling, CSRF validation, and audit logging.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.security.password_hashing import hash_password


@pytest.fixture
def secure_client(db_engine: Engine) -> TestClient:
    """Client backed by a test app with full middleware stack."""
    from fastapi import FastAPI
    from sqlmodel import Session as SqlSession

    from captive_portal.api.routes import (
        admin_auth,
        vouchers_ui,
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
    test_app.include_router(vouchers_ui.router)

    def get_test_session() -> Generator[Any, None, None]:
        """Return a test database session."""
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


def _create_voucher(
    db_session: Session,
    *,
    code: str,
    status: VoucherStatus = VoucherStatus.EXPIRED,
    duration_minutes: int = 60,
    status_changed_utc: datetime | None = None,
) -> Voucher:
    """Persist a voucher for integration testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        status_changed_utc=status_changed_utc,
    )
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


@pytest.mark.integration
class TestAdminVoucherPurgeFlow:
    """T017: Integration tests for manual purge UI flow."""

    def test_purge_preview_with_valid_input(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """POST purge-preview with valid N redirects with count."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _create_voucher(db_session, code="PRGPREV001", status_changed_utc=old_time)

        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": "30"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "purge_preview_count=" in location
        assert "purge_preview_days=30" in location

    def test_purge_preview_banner_rendering(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Preview banner shows correct count and days in rendered page."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _create_voucher(db_session, code="PRGBNR0001", status_changed_utc=old_time)

        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": "30"},
            follow_redirects=False,
        )
        location = resp.headers["location"]
        page = client.get(location)
        assert page.status_code == 200
        body = page.text
        assert "1 voucher(s)" in body
        assert "Confirm Purge" in body

    def test_purge_confirm_executes_purge(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """POST purge-confirm deletes vouchers and redirects with success."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _create_voucher(db_session, code="PRGCONF001", status_changed_utc=old_time)

        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-confirm",
            data={"csrf_token": csrf_token, "min_age_days": "30"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        assert "Purged" in location

        # Verify voucher is deleted
        from captive_portal.persistence.repositories import VoucherRepository

        with Session(db_session.get_bind()) as check_session:
            repo = VoucherRepository(check_session)
            assert repo.get_by_code("PRGCONF001") is None

    def test_purge_zero_means_all_terminal(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """N=0 purges all terminal vouchers regardless of age."""
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        _create_voucher(db_session, code="PRGZRO0001", status_changed_utc=recent)
        _create_voucher(
            db_session, code="PRGZRO0002", status=VoucherStatus.REVOKED, status_changed_utc=recent
        )

        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": "0"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "purge_preview_count=2" in location

    def test_invalid_input_negative_number(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """Negative number redirects with error."""
        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": "-5"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location

    def test_invalid_input_non_integer(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """Non-integer input redirects with error."""
        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": "abc"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location

    def test_invalid_input_empty(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """Empty input redirects with error."""
        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location

    def test_zero_eligible_shows_info_message(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """When no vouchers match, redirect includes info message."""
        client, csrf_token = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": csrf_token, "min_age_days": "30"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "info=" in location

    def test_csrf_validation_on_preview(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """CSRF failure on preview returns error redirect."""
        client, _ = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-preview",
            data={"csrf_token": "invalid-token", "min_age_days": "30"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error=" in resp.headers["location"]

    def test_csrf_validation_on_confirm(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """CSRF failure on confirm returns error redirect."""
        client, _ = authed_secure_client
        resp = client.post(
            "/admin/vouchers/purge-confirm",
            data={"csrf_token": "invalid-token", "min_age_days": "30"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error=" in resp.headers["location"]

    def test_manual_purge_creates_audit_entry(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Manual purge creates audit entry with admin username."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        _create_voucher(db_session, code="AUDPRG0001", status_changed_utc=old_time)

        client, csrf_token = authed_secure_client
        client.post(
            "/admin/vouchers/purge-confirm",
            data={"csrf_token": csrf_token, "min_age_days": "30"},
            follow_redirects=False,
        )

        stmt: Any = select(AuditLog).where(AuditLog.action == "voucher.manual_purge")
        entries = list(db_session.exec(stmt).all())
        assert len(entries) >= 1
        entry = entries[-1]
        assert entry.actor == "testadmin"
        assert entry.meta["purged_count"] == 1

    def test_purge_form_visible_on_page(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """The purge form section is visible on the admin vouchers page."""
        client, _ = authed_secure_client
        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200
        body = resp.text
        assert "Purge Expired/Revoked Vouchers" in body
        assert "min_age_days" in body
        assert "Preview Purge" in body
