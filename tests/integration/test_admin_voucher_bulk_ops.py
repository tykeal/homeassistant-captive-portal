# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T021 - Integration tests for admin voucher bulk operations."""

from __future__ import annotations

import urllib.parse
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
    code: str,
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


def _cleanup(db_session: Session, codes: list[str]) -> None:
    """Remove any remaining vouchers by code."""
    for code in codes:
        v = db_session.get(Voucher, code)
        if v is not None:
            db_session.delete(v)
    db_session.commit()


@pytest.mark.integration
class TestBulkRevokeIntegration:
    """T021: Bulk revoke end-to-end flows."""

    def test_bulk_revoke_all_unused(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Select 3 unused -> bulk-revoke -> all revoked with success summary."""
        client, csrf = authenticated_client
        codes = ["BLKREV001", "BLKREV002", "BLKREV003"]
        for c in codes:
            _create_voucher(db_session, code=c)

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

        _cleanup(db_session, codes)

    def test_bulk_revoke_mixed(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Mix of unused + expired + revoked -> partial success summary."""
        client, csrf = authenticated_client
        codes = ["BLKMIX001", "BLKMIX002", "BLKMIX003"]
        _create_voucher(db_session, code="BLKMIX001")
        _create_voucher(
            db_session,
            code="BLKMIX002",
            duration_minutes=1,
            created_utc=datetime.now(timezone.utc) - timedelta(hours=24),
        )
        _create_voucher(db_session, code="BLKMIX003", status=VoucherStatus.REVOKED)

        resp = client.post(
            "/admin/vouchers/bulk-revoke",
            data={"csrf_token": csrf, "codes": codes},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        decoded = urllib.parse.unquote_plus(location)
        assert "success=" in location
        assert "skipped" in decoded.lower()

        _cleanup(db_session, codes)

    def test_bulk_revoke_no_selection(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """No vouchers selected -> error message."""
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


@pytest.mark.integration
class TestBulkDeleteIntegration:
    """T021: Bulk delete end-to-end flows."""

    def test_bulk_delete_all_unused(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Select 3 unused -> bulk-delete -> all removed with success summary."""
        client, csrf = authenticated_client
        codes = ["BLKDEL001", "BLKDEL002", "BLKDEL003"]
        for c in codes:
            _create_voucher(db_session, code=c)

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

        for c in codes:
            assert db_session.get(Voucher, c) is None

    def test_bulk_delete_mixed_with_redeemed(
        self,
        authenticated_client: tuple[TestClient, str],
        db_session: Session,
    ) -> None:
        """Mix of unused + redeemed -> partial success."""
        client, csrf = authenticated_client
        codes = ["BLKDLM001", "BLKDLM002", "BLKDLM003"]
        _create_voucher(db_session, code="BLKDLM001")
        _create_voucher(db_session, code="BLKDLM002")
        _create_voucher(
            db_session,
            code="BLKDLM003",
            redeemed_count=1,
            status=VoucherStatus.ACTIVE,
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

        _cleanup(db_session, codes)

    def test_bulk_delete_no_selection(
        self,
        authenticated_client: tuple[TestClient, str],
    ) -> None:
        """No vouchers selected -> error message."""
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
