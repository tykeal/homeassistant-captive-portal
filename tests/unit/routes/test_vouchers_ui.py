# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for admin vouchers UI routes (T021, T022).

Tests the vouchers_ui route module which provides:
- GET /admin/vouchers — list vouchers with new_code highlight (T021)
- POST /admin/vouchers/create — create new voucher (T022)

These are TDD tests written before implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.voucher import Voucher, VoucherStatus
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
def vouchers_app(db_engine: Engine) -> FastAPI:
    """App with vouchers UI routes for unit testing."""
    from captive_portal.api.routes import admin_auth, vouchers_ui

    test_app = FastAPI()
    session_config = SessionConfig(cookie_secure=False)
    session_store = SessionStore()
    test_app.state.session_config = session_config
    test_app.state.session_store = session_store
    test_app.add_middleware(SessionMiddleware, config=session_config, store=session_store)
    test_app.include_router(vouchers_ui.router)
    test_app.include_router(admin_auth.router)

    def get_test_session() -> Generator[Session, None, None]:
        """Return a fake admin session for testing."""
        with Session(db_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = get_test_session
    return test_app


@pytest.fixture
def vouchers_client(vouchers_app: FastAPI) -> TestClient:
    """TestClient wired to the vouchers UI app."""
    return TestClient(vouchers_app)


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
def authenticated_client(vouchers_client: TestClient, admin_user: Any) -> tuple[TestClient, str]:
    """Returns (client, csrf_token) after login."""
    resp = vouchers_client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    vouchers_client.cookies.set("csrftoken", csrf_token)
    return vouchers_client, csrf_token


def _make_voucher(
    db_session: Session,
    *,
    code: str = "ABCD1234",
    duration_minutes: int = 60,
    status: VoucherStatus = VoucherStatus.UNUSED,
    redeemed_count: int = 0,
    booking_ref: str | None = None,
    last_redeemed_utc: datetime | None = None,
) -> Voucher:
    """Helper to create and persist a voucher."""
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
# T021 – GET /admin/vouchers
# ---------------------------------------------------------------------------


class TestGetVouchersPage:
    """T021: GET /admin/vouchers — list vouchers with new_code highlight."""

    def test_authenticated_get_returns_200_html(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """Authenticated GET should return 200 with HTML content."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/vouchers")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_unauthenticated_get_returns_401(self, vouchers_client: TestClient) -> None:
        """Unauthenticated GET should return 401."""
        resp = vouchers_client.get("/admin/vouchers")
        assert resp.status_code == 401

    def test_voucher_listing_shows_codes(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Voucher codes should appear in the rendered HTML."""
        client, _csrf = authenticated_client

        v1 = _make_voucher(db_session, code="TESTCODE01")
        v2 = _make_voucher(db_session, code="TESTCODE02", duration_minutes=120)

        resp = client.get("/admin/vouchers")
        assert resp.status_code == 200
        body = resp.text

        assert "TESTCODE01" in body
        assert "TESTCODE02" in body

        for v in (v1, v2):
            db_session.delete(v)
        db_session.commit()

    def test_derived_status_unredeemed(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Voucher with redeemed_count=0 should show 'Unredeemed' status."""
        client, _csrf = authenticated_client

        v = _make_voucher(db_session, code="UNREDEEM01", redeemed_count=0)

        resp = client.get("/admin/vouchers")
        assert resp.status_code == 200
        assert "Unredeemed" in resp.text

        db_session.delete(v)
        db_session.commit()

    def test_derived_status_redeemed(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Voucher with redeemed_count>0 should show 'Redeemed' status."""
        client, _csrf = authenticated_client

        v = _make_voucher(
            db_session,
            code="REDEEMED01",
            redeemed_count=3,
            status=VoucherStatus.ACTIVE,
            last_redeemed_utc=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
        )

        resp = client.get("/admin/vouchers")
        assert resp.status_code == 200
        assert "Redeemed" in resp.text

        db_session.delete(v)
        db_session.commit()

    def test_empty_state_shows_no_vouchers_found(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """When no vouchers exist, page should display 'No vouchers found'."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/vouchers")
        assert resp.status_code == 200
        assert "No vouchers found" in resp.text

    def test_new_code_query_param_displayed(
        self, authenticated_client: tuple[TestClient, str]
    ) -> None:
        """new_code query param should be displayed prominently in HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/vouchers?new_code=FRESH12345")
        assert resp.status_code == 200
        assert "FRESH12345" in resp.text

    def test_success_message_displayed(self, authenticated_client: tuple[TestClient, str]) -> None:
        """Success query param should be reflected in the rendered HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/vouchers?success=Voucher+created+successfully")
        assert resp.status_code == 200
        assert "Voucher created successfully" in resp.text

    def test_error_message_displayed(self, authenticated_client: tuple[TestClient, str]) -> None:
        """Error query param should be reflected in the rendered HTML."""
        client, _csrf = authenticated_client
        resp = client.get("/admin/vouchers?error=Failed+to+generate+unique+voucher+code")
        assert resp.status_code == 200
        assert "Failed to generate unique voucher code" in resp.text


# ---------------------------------------------------------------------------
# T022 – POST /admin/vouchers/create
# ---------------------------------------------------------------------------


class TestCreateVoucher:
    """T022: POST /admin/vouchers/create — create new voucher."""

    def test_successful_create_redirects_with_new_code(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """Valid create request should 303 redirect with new_code and success."""
        client, csrf_token = authenticated_client

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

    def test_invalid_csrf_redirects_with_error(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """Invalid CSRF token should 303 redirect with error."""
        client, _csrf = authenticated_client

        resp = client.post(
            "/admin/vouchers/create",
            data={"csrf_token": "wrong-token-value", "duration_minutes": "60"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "csrf" in location.lower() or "CSRF" in location

    @pytest.mark.parametrize(
        "duration_value,desc",
        [
            ("0", "zero"),
            ("-5", "negative"),
            ("43201", "exceeds max"),
            ("abc", "non-numeric"),
        ],
    )
    def test_invalid_duration_redirects_with_error(
        self,
        authenticated_client: tuple[TestClient, str],
        duration_value: str,
        desc: str,
    ) -> None:
        """Invalid duration values should 303 redirect with error."""
        client, csrf_token = authenticated_client

        resp = client.post(
            "/admin/vouchers/create",
            data={
                "csrf_token": csrf_token,
                "duration_minutes": duration_value,
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert (
            "duration" in location.lower()
            or "Duration" in location
            or "1" in location
            or "43200" in location
        )

    def test_optional_booking_ref_included(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """Optional booking_ref should be accepted on create."""
        client, csrf_token = authenticated_client

        resp = client.post(
            "/admin/vouchers/create",
            data={
                "csrf_token": csrf_token,
                "duration_minutes": "120",
                "booking_ref": "BOOK-REF-999",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/admin/vouchers" in location
        assert "new_code=" in location
        assert "success=" in location

    def test_collision_error_redirects_with_error(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """VoucherCollisionError should 303 redirect with error message."""
        from unittest.mock import AsyncMock, patch

        from captive_portal.services.voucher_service import VoucherCollisionError

        client, csrf_token = authenticated_client

        with patch(
            "captive_portal.services.voucher_service.VoucherService.create",
            new_callable=AsyncMock,
            side_effect=VoucherCollisionError("Failed to generate unique voucher code"),
        ):
            resp = client.post(
                "/admin/vouchers/create",
                data={
                    "csrf_token": csrf_token,
                    "duration_minutes": "60",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "unique" in location.lower() or "voucher+code" in location.lower()

    def test_invalid_csrf_logging(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Invalid CSRF on create should produce structured log."""
        client, _csrf = authenticated_client

        with caplog.at_level(logging.WARNING):
            client.post(
                "/admin/vouchers/create",
                data={
                    "csrf_token": "wrong-token-value",
                    "duration_minutes": "60",
                },
                follow_redirects=False,
            )

        csrf_logs = [
            r
            for r in caplog.records
            if "csrf" in r.getMessage().lower() or "CSRF" in r.getMessage()
        ]
        assert len(csrf_logs) >= 1

    def test_invalid_duration_logging(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Invalid duration on create should produce structured log."""
        client, csrf_token = authenticated_client

        with caplog.at_level(logging.WARNING):
            client.post(
                "/admin/vouchers/create",
                data={
                    "csrf_token": csrf_token,
                    "duration_minutes": "abc",
                },
                follow_redirects=False,
            )

        duration_logs = [
            r
            for r in caplog.records
            if "duration" in r.getMessage().lower() or "minutes" in r.getMessage().lower()
        ]
        assert len(duration_logs) >= 1

    def test_collision_error_logging(
        self,
        authenticated_client: tuple[TestClient, str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """VoucherCollisionError should produce structured log."""
        from unittest.mock import AsyncMock, patch

        from captive_portal.services.voucher_service import VoucherCollisionError

        client, csrf_token = authenticated_client

        with (
            patch(
                "captive_portal.services.voucher_service.VoucherService.create",
                new_callable=AsyncMock,
                side_effect=VoucherCollisionError("Failed to generate unique voucher code"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            client.post(
                "/admin/vouchers/create",
                data={
                    "csrf_token": csrf_token,
                    "duration_minutes": "60",
                },
                follow_redirects=False,
            )

        collision_logs = [
            r
            for r in caplog.records
            if "collision" in r.getMessage().lower()
            or "unique" in r.getMessage().lower()
            or "voucher" in r.getMessage().lower()
        ]
        assert len(collision_logs) >= 1
