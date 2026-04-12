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
import re
import urllib.parse
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
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

from captive_portal.api.routes.vouchers_ui import BulkResult, format_bulk_message


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


# ---------------------------------------------------------------------------
# T003 – Voucher actions context (can_revoke / can_delete buttons)
# ---------------------------------------------------------------------------


class TestVoucherActionsContext:
    """T003: GET /admin/vouchers/ returns per-voucher action buttons."""

    def test_unused_voucher_buttons_enabled(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Unused voucher: revoke enabled, delete enabled."""
        client, _csrf = authenticated_client
        v = _make_voucher(db_session, code="ACTUNUSED1")

        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200

        revoke_btn = re.search(r'formaction="[^"]*revoke/ACTUNUSED1"[^>]*>', resp.text)
        assert revoke_btn is not None
        assert "disabled" not in revoke_btn.group()

        delete_btn = re.search(r'formaction="[^"]*delete/ACTUNUSED1"[^>]*>', resp.text)
        assert delete_btn is not None
        assert "disabled" not in delete_btn.group()

        db_session.delete(v)
        db_session.commit()

    def test_expired_voucher_revoke_disabled(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Expired voucher: revoke disabled, delete enabled (unredeemed)."""
        client, _csrf = authenticated_client
        past = datetime.now(timezone.utc) - timedelta(hours=24)
        v = Voucher(
            code="ACTEXPRD01",
            duration_minutes=1,
            created_utc=past,
            activated_utc=past,
        )
        db_session.add(v)
        db_session.commit()
        db_session.refresh(v)

        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200

        revoke_btn = re.search(r'formaction="[^"]*revoke/ACTEXPRD01"[^>]*>', resp.text)
        assert revoke_btn is not None
        assert "disabled" in revoke_btn.group()

        delete_btn = re.search(r'formaction="[^"]*delete/ACTEXPRD01"[^>]*>', resp.text)
        assert delete_btn is not None
        assert "disabled" not in delete_btn.group()

        db_session.delete(v)
        db_session.commit()

    def test_revoked_voucher_revoke_disabled(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoked voucher: revoke disabled, delete enabled (unredeemed)."""
        client, _csrf = authenticated_client
        v = _make_voucher(db_session, code="ACTREVKD01", status=VoucherStatus.REVOKED)

        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200

        revoke_btn = re.search(r'formaction="[^"]*revoke/ACTREVKD01"[^>]*>', resp.text)
        assert revoke_btn is not None
        assert "disabled" in revoke_btn.group()

        delete_btn = re.search(r'formaction="[^"]*delete/ACTREVKD01"[^>]*>', resp.text)
        assert delete_btn is not None
        assert "disabled" not in delete_btn.group()

        db_session.delete(v)
        db_session.commit()

    def test_redeemed_voucher_delete_disabled(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Active+redeemed voucher: revoke enabled, delete disabled."""
        client, _csrf = authenticated_client
        v = _make_voucher(
            db_session,
            code="ACTREDMD01",
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
        )

        resp = client.get("/admin/vouchers/")
        assert resp.status_code == 200

        revoke_btn = re.search(r'formaction="[^"]*revoke/ACTREDMD01"[^>]*>', resp.text)
        assert revoke_btn is not None
        assert "disabled" not in revoke_btn.group()

        delete_btn = re.search(r'formaction="[^"]*delete/ACTREDMD01"[^>]*>', resp.text)
        assert delete_btn is not None
        assert "disabled" in delete_btn.group()

        db_session.delete(v)
        db_session.commit()


# ---------------------------------------------------------------------------
# T007 – POST /admin/vouchers/revoke/{code}
# ---------------------------------------------------------------------------


class TestRevokeVoucher:
    """T007: POST /admin/vouchers/revoke/{code} — revoke voucher."""

    def test_successful_revoke(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Valid revoke request should 303 redirect with success message."""
        client, csrf_token = authenticated_client
        v = _make_voucher(db_session, code="REVOKEU001")

        resp = client.post(
            "/admin/vouchers/revoke/REVOKEU001",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        assert "revoked" in location.lower()

        db_session.delete(v)
        db_session.commit()

    def test_revoke_already_revoked_idempotent(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoking already-revoked voucher should succeed (idempotent FR-004)."""
        client, csrf_token = authenticated_client
        v = _make_voucher(db_session, code="REVOKEI001", status=VoucherStatus.REVOKED)

        resp = client.post(
            "/admin/vouchers/revoke/REVOKEI001",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location

        db_session.delete(v)
        db_session.commit()

    def test_revoke_not_found(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """Revoking non-existent voucher should redirect with error."""
        client, csrf_token = authenticated_client

        resp = client.post(
            "/admin/vouchers/revoke/NOEXIST001",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "not+found" in location.lower() or "not found" in location.lower()

    def test_revoke_expired_voucher(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoking an expired voucher should redirect with error."""
        client, csrf_token = authenticated_client
        past = datetime.now(timezone.utc) - timedelta(hours=24)
        v = Voucher(
            code="REVOKEEXP1",
            duration_minutes=1,
            created_utc=past,
            activated_utc=past,
        )
        db_session.add(v)
        db_session.commit()
        db_session.refresh(v)

        resp = client.post(
            "/admin/vouchers/revoke/REVOKEEXP1",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "expired" in location.lower()

        db_session.delete(v)
        db_session.commit()

    def test_revoke_invalid_csrf(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Invalid CSRF token should redirect with error."""
        client, _csrf = authenticated_client
        v = _make_voucher(db_session, code="REVOKECSR1")

        resp = client.post(
            "/admin/vouchers/revoke/REVOKECSR1",
            data={"csrf_token": "wrong-token-value"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "csrf" in location.lower() or "CSRF" in location

        db_session.delete(v)
        db_session.commit()


# ---------------------------------------------------------------------------
# T013 – POST /admin/vouchers/delete/{code}
# ---------------------------------------------------------------------------


class TestDeleteVoucher:
    """T013: POST /admin/vouchers/delete/{code} — delete voucher."""

    def test_successful_delete(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Valid delete request should 303 redirect with success message."""
        client, csrf_token = authenticated_client
        _make_voucher(db_session, code="DELETEU001")

        resp = client.post(
            "/admin/vouchers/delete/DELETEU001",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        assert "deleted" in location.lower()

    def test_delete_redeemed_voucher(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Deleting a redeemed voucher should redirect with error."""
        client, csrf_token = authenticated_client
        v = _make_voucher(
            db_session,
            code="DELETERD01",
            status=VoucherStatus.ACTIVE,
            redeemed_count=2,
        )

        resp = client.post(
            "/admin/vouchers/delete/DELETERD01",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "redeemed" in location.lower()

        db_session.delete(v)
        db_session.commit()

    def test_delete_not_found(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """Deleting non-existent voucher should redirect with error."""
        client, csrf_token = authenticated_client

        resp = client.post(
            "/admin/vouchers/delete/NOEXIST002",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "not+found" in location.lower() or "not found" in location.lower()

    def test_delete_invalid_csrf(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Invalid CSRF token should redirect with error."""
        client, _csrf = authenticated_client
        v = _make_voucher(db_session, code="DELETECSR1")

        resp = client.post(
            "/admin/vouchers/delete/DELETECSR1",
            data={"csrf_token": "wrong-token-value"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        assert "csrf" in location.lower() or "CSRF" in location

        db_session.delete(v)
        db_session.commit()


# ---------------------------------------------------------------------------
# T019 – BulkResult + format_bulk_message
# ---------------------------------------------------------------------------


class TestBulkResultFormatting:
    """T019: BulkResult dataclass and format_bulk_message helper."""

    def test_all_success_revoke(self) -> None:
        """All-success message for revoke."""
        result = BulkResult(action="revoked", success_count=5)
        msg, key = format_bulk_message(result)
        assert "5 vouchers" in msg.lower()
        assert "successfully" in msg.lower()
        assert key == "success"

    def test_partial_success_revoke(self) -> None:
        """Partial success with skips."""
        result = BulkResult(
            action="revoked",
            success_count=3,
            skip_reasons={"expired": 1, "already revoked": 1},
        )
        msg, key = format_bulk_message(result)
        assert "3 vouchers" in msg.lower()
        assert "skipped" in msg.lower()
        assert key == "success"

    def test_all_skipped(self) -> None:
        """All vouchers skipped."""
        result = BulkResult(
            action="revoked",
            success_count=0,
            skip_reasons={"expired": 2, "already revoked": 1},
        )
        msg, key = format_bulk_message(result)
        assert "skipped" in msg.lower()
        assert key == "error"

    def test_all_success_delete(self) -> None:
        """All-success message for delete variant."""
        result = BulkResult(action="deleted", success_count=4)
        msg, key = format_bulk_message(result)
        assert "4 vouchers" in msg.lower()
        assert "successfully" in msg.lower()
        assert key == "success"


# ---------------------------------------------------------------------------
# T020 – POST /admin/vouchers/bulk-revoke
# ---------------------------------------------------------------------------


class TestBulkRevokeVouchers:
    """T020: POST /admin/vouchers/bulk-revoke — bulk revoke."""

    def test_bulk_revoke_all_success(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """All selected vouchers revoked -> success redirect."""
        client, csrf = authenticated_client
        codes = ["BULKREV001", "BULKREV002", "BULKREV003"]
        for c in codes:
            _make_voucher(db_session, code=c)

        resp = client.post(
            "/admin/vouchers/bulk-revoke",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        decoded = urllib.parse.unquote_plus(location)
        assert "3 vouchers" in decoded.lower()

        for c in codes:
            v = db_session.get(Voucher, c)
            if v:
                db_session.delete(v)
        db_session.commit()

    def test_bulk_revoke_partial_success(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Mixed eligibility -> success redirect with skipped summary."""
        client, csrf = authenticated_client
        codes = ["BULKRVP001", "BULKRVP002"]
        _make_voucher(db_session, code="BULKRVP001")
        _make_voucher(db_session, code="BULKRVP002", status=VoucherStatus.REVOKED)

        resp = client.post(
            "/admin/vouchers/bulk-revoke",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        decoded = urllib.parse.unquote_plus(location)
        assert "skipped" in decoded.lower()

        for c in codes:
            v = db_session.get(Voucher, c)
            if v:
                db_session.delete(v)
        db_session.commit()

    def test_bulk_revoke_all_skipped(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """All ineligible -> error redirect."""
        client, csrf = authenticated_client
        codes = ["BULKRVS001", "BULKRVS002"]
        _make_voucher(db_session, code="BULKRVS001", status=VoucherStatus.REVOKED)
        _make_voucher(db_session, code="BULKRVS002", status=VoucherStatus.REVOKED)

        resp = client.post(
            "/admin/vouchers/bulk-revoke",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location

        for c in codes:
            v = db_session.get(Voucher, c)
            if v:
                db_session.delete(v)
        db_session.commit()

    def test_bulk_revoke_no_selection(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """No vouchers selected -> error redirect."""
        client, csrf = authenticated_client

        resp = client.post(
            "/admin/vouchers/bulk-revoke",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        decoded = urllib.parse.unquote_plus(location)
        assert "no" in decoded.lower() and "selected" in decoded.lower()


# ---------------------------------------------------------------------------
# T020 – POST /admin/vouchers/bulk-delete
# ---------------------------------------------------------------------------


class TestBulkDeleteVouchers:
    """T020: POST /admin/vouchers/bulk-delete — bulk delete."""

    def test_bulk_delete_all_success(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """All selected vouchers deleted -> success redirect."""
        client, csrf = authenticated_client
        codes = ["BULKDEL001", "BULKDEL002", "BULKDEL003"]
        for c in codes:
            _make_voucher(db_session, code=c)

        resp = client.post(
            "/admin/vouchers/bulk-delete",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        decoded = urllib.parse.unquote_plus(location)
        assert "3 vouchers" in decoded.lower()

    def test_bulk_delete_partial_success(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Mixed eligibility -> success redirect with skipped summary."""
        client, csrf = authenticated_client
        codes = ["BULKDLP001", "BULKDLP002"]
        _make_voucher(db_session, code="BULKDLP001")
        _make_voucher(
            db_session,
            code="BULKDLP002",
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
        )

        resp = client.post(
            "/admin/vouchers/bulk-delete",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        decoded = urllib.parse.unquote_plus(location)
        assert "skipped" in decoded.lower()

        v = db_session.get(Voucher, "BULKDLP002")
        if v:
            db_session.delete(v)
        db_session.commit()

    def test_bulk_delete_all_skipped(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """All ineligible -> error redirect."""
        client, csrf = authenticated_client
        codes = ["BULKDLS001", "BULKDLS002"]
        _make_voucher(
            db_session,
            code="BULKDLS001",
            status=VoucherStatus.ACTIVE,
            redeemed_count=1,
        )
        _make_voucher(
            db_session,
            code="BULKDLS002",
            status=VoucherStatus.ACTIVE,
            redeemed_count=2,
        )

        resp = client.post(
            "/admin/vouchers/bulk-delete",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location

        for c in codes:
            v = db_session.get(Voucher, c)
            if v:
                db_session.delete(v)
        db_session.commit()

    def test_bulk_delete_no_selection(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """No vouchers selected -> error redirect."""
        client, csrf = authenticated_client

        resp = client.post(
            "/admin/vouchers/bulk-delete",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "error=" in location
        decoded = urllib.parse.unquote_plus(location)
        assert "no" in decoded.lower() and "selected" in decoded.lower()
