# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T014 - Integration tests for admin voucher delete flow."""

from __future__ import annotations

import re
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.security.password_hashing import hash_password


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
def authenticated_client(client: TestClient, admin_user: Any) -> tuple[TestClient, str]:
    """Returns (client, csrf_token) after login."""
    resp = client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    client.cookies.set("csrftoken", csrf_token)
    return client, csrf_token


def _create_voucher(
    db_session: Session,
    *,
    code: str = "INTEGDEL01",
    duration_minutes: int = 60,
    status: VoucherStatus = VoucherStatus.UNUSED,
    redeemed_count: int = 0,
) -> Voucher:
    """Persist a voucher for integration testing."""
    voucher = Voucher(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
    )
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


@pytest.mark.integration
class TestAdminVoucherDelete:
    """T014: Full-page delete flow with enabled/disabled buttons."""

    def test_delete_unused_full_flow(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Create unused -> GET (enabled delete) -> POST delete -> GET gone."""
        client, csrf = authenticated_client
        _create_voucher(db_session, code="INTDEL001")

        page = client.get("/admin/vouchers/")
        assert page.status_code == 200
        btn = re.search(r'formaction="[^"]*delete/INTDEL001"[^>]*>', page.text)
        assert btn is not None
        assert "disabled" not in btn.group()

        resp = client.post(
            "/admin/vouchers/delete/INTDEL001",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        assert "deleted" in location.lower()

        page2 = client.get(location)
        assert page2.status_code == 200
        assert "<code>INTDEL001</code>" not in page2.text

    def test_redeemed_voucher_shows_disabled_delete(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Redeemed voucher has a disabled delete button."""
        client, _csrf = authenticated_client
        v = _create_voucher(
            db_session,
            code="INTDELRD01",
            redeemed_count=2,
            status=VoucherStatus.ACTIVE,
        )

        page = client.get("/admin/vouchers/")
        assert page.status_code == 200
        btn = re.search(r'formaction="[^"]*delete/INTDELRD01"[^>]*>', page.text)
        assert btn is not None
        assert "disabled" in btn.group()

        db_session.delete(v)
        db_session.commit()

    def test_delete_revoked_unredeemed_voucher(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Revoked but unredeemed voucher can be deleted (FR-009)."""
        client, csrf = authenticated_client
        _create_voucher(
            db_session,
            code="INTDELRV01",
            status=VoucherStatus.REVOKED,
            redeemed_count=0,
        )

        resp = client.post(
            "/admin/vouchers/delete/INTDELRV01",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location

        page = client.get(location)
        assert page.status_code == 200
        assert "<code>INTDELRV01</code>" not in page.text
