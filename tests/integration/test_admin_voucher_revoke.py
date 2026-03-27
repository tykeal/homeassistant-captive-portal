# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T008 - Integration tests for admin voucher revoke flow."""

from __future__ import annotations

import re
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
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
    code: str = "INTEGREV01",
    duration_minutes: int = 60,
    status: VoucherStatus = VoucherStatus.UNUSED,
    redeemed_count: int = 0,
    created_utc: datetime | None = None,
) -> Voucher:
    """Persist a voucher for integration testing."""
    kwargs: dict[str, Any] = dict(
        code=code,
        duration_minutes=duration_minutes,
        status=status,
        redeemed_count=redeemed_count,
    )
    if created_utc is not None:
        kwargs["created_utc"] = created_utc
    voucher = Voucher(**kwargs)
    db_session.add(voucher)
    db_session.commit()
    db_session.refresh(voucher)
    return voucher


@pytest.mark.integration
class TestAdminVoucherRevoke:
    """T008: Full-page revoke flow with enabled/disabled buttons."""

    def test_revoke_unused_full_flow(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Create -> GET (enabled) -> POST revoke -> GET (REVOKED + disabled)."""
        client, csrf = authenticated_client
        _create_voucher(db_session, code="INTGREV001")

        page = client.get("/admin/vouchers/")
        assert page.status_code == 200
        btn = re.search(r'formaction="[^"]*revoke/INTGREV001"[^>]*>', page.text)
        assert btn is not None
        assert "disabled" not in btn.group()

        resp = client.post(
            "/admin/vouchers/revoke/INTGREV001",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "success=" in location
        assert "revoked" in location.lower()

        page2 = client.get(location)
        assert page2.status_code == 200
        assert "status-revoked" in page2.text
        btn2 = re.search(r'formaction="[^"]*revoke/INTGREV001"[^>]*>', page2.text)
        assert btn2 is not None
        assert "disabled" in btn2.group()

        refreshed = db_session.get(Voucher, "INTGREV001")
        if refreshed:
            db_session.delete(refreshed)
            db_session.commit()

    def test_expired_voucher_shows_disabled_revoke(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Expired voucher has a disabled revoke button."""
        client, _csrf = authenticated_client
        v = _create_voucher(
            db_session,
            code="INTGEXP001",
            duration_minutes=1,
            created_utc=datetime.now(timezone.utc) - timedelta(hours=24),
        )

        page = client.get("/admin/vouchers/")
        assert page.status_code == 200
        btn = re.search(r'formaction="[^"]*revoke/INTGEXP001"[^>]*>', page.text)
        assert btn is not None
        assert "disabled" in btn.group()

        db_session.delete(v)
        db_session.commit()

    def test_revoked_voucher_shows_disabled_revoke(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Already-revoked voucher has a disabled revoke button."""
        client, _csrf = authenticated_client
        v = _create_voucher(
            db_session,
            code="INTGRVK001",
            status=VoucherStatus.REVOKED,
        )

        page = client.get("/admin/vouchers/")
        assert page.status_code == 200
        btn = re.search(r'formaction="[^"]*revoke/INTGRVK001"[^>]*>', page.text)
        assert btn is not None
        assert "disabled" in btn.group()

        db_session.delete(v)
        db_session.commit()
