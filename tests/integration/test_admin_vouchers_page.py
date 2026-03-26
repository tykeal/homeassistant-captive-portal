# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T023 – Integration tests for admin vouchers page.

Full-page integration tests using the complete middleware stack
(SecurityHeadersMiddleware, SessionMiddleware) to verify the vouchers
management page renders correctly and PRG flows work end-to-end.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser
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


def _create_voucher(
    db_session: Session,
    *,
    code: str = "INTEGTEST1",
    duration_minutes: int = 60,
    status: VoucherStatus = VoucherStatus.UNUSED,
    redeemed_count: int = 0,
    booking_ref: str | None = None,
    last_redeemed_utc: datetime | None = None,
) -> Voucher:
    """Persist a voucher for integration testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
        booking_ref=booking_ref,
        last_redeemed_utc=last_redeemed_utc,
    )
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


# ---------------------------------------------------------------------------
# T023 – Full page integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdminVouchersPage:
    """T023: Full-page integration tests for /admin/vouchers."""

    def test_unauthenticated_returns_401(self, secure_client: TestClient) -> None:
        """Unauthenticated request to vouchers page should return 401."""
        resp = secure_client.get("/admin/vouchers/", follow_redirects=False)
        assert resp.status_code == 401

    def test_authenticated_page_load_returns_200(
        self, authed_secure_client: tuple[TestClient, str]
    ) -> None:
        """Authenticated GET /admin/vouchers should return 200 HTML."""
        client, _csrf = authed_secure_client
        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_voucher_list_rendering(
        self,
        authed_secure_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """HTML should contain voucher codes and booking refs."""
        client, _csrf = authed_secure_client

        v1 = _create_voucher(
            db_session,
            code="INTGVCH001",
            duration_minutes=90,
            booking_ref="BK-INTEG-1",
        )
        v2 = _create_voucher(
            db_session,
            code="INTGVCH002",
            duration_minutes=180,
            redeemed_count=2,
            status=VoucherStatus.ACTIVE,
            last_redeemed_utc=datetime(2025, 3, 1, 10, 0, tzinfo=timezone.utc),
        )

        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200
        body = resp.text

        assert "INTGVCH001" in body
        assert "INTGVCH002" in body

        for v in (v1, v2):
            db_session.delete(v)
        db_session.commit()

    def test_create_voucher_prg_redirect(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """POST create should 303 redirect and following GET shows success."""
        client, csrf_token = authed_secure_client

        # POST → 303 redirect
        resp = client.post(
            "/admin/vouchers/create",
            data={"csrf_token": csrf_token, "duration_minutes": "60"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/admin/vouchers" in location
        assert "new_code=" in location
        assert "success=" in location

        # Follow the redirect manually to verify page renders
        get_resp = client.get(location)
        assert get_resp.status_code == 200
        assert "text/html" in get_resp.headers["content-type"]

    def test_new_code_prominent_display(
        self,
        authed_secure_client: tuple[TestClient, str],
    ) -> None:
        """After create, the new_code should be prominently displayed."""
        client, csrf_token = authed_secure_client

        # Create a voucher to get a real code
        resp = client.post(
            "/admin/vouchers/create",
            data={"csrf_token": csrf_token, "duration_minutes": "120"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]

        # Extract new_code from redirect location
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        assert "new_code" in params
        new_code = params["new_code"][0]

        # Follow redirect and verify code is in the page
        get_resp = client.get(location)
        assert get_resp.status_code == 200
        assert new_code in get_resp.text

    def test_empty_state_display(self, authed_secure_client: tuple[TestClient, str]) -> None:
        """When no vouchers exist, the page should show empty state."""
        client, _csrf = authed_secure_client
        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No vouchers found" in resp.text
