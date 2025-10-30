# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for audit log completeness across all operations."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.persistence.database import get_session
from captive_portal.security.password_hashing import hash_password

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_audit_log_admin_login(async_client: "AsyncClient") -> None:
    """Verify admin login operations are audited."""
    # GIVEN: Admin user
    session = next(get_session())
    try:
        admin = AdminUser(
            username="audit_login_test",
            password_hash=hash_password("test_password"),
            email="audit_login_test@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Admin logs in
    client = async_client
    response = await client.post(
        "/admin/login",
        data={"username": "audit_login_test", "password": "test_password"},
    )
    assert response.status_code == 200

    # THEN: Audit log contains login event
    session = next(get_session())
    try:
        audit_entries = session.exec(
            select(AuditLog)
            .where(AuditLog.actor == "audit_login_test")
            .where(
                AuditLog.action.like("%login%")  # type: ignore[attr-defined]
            )
        ).all()
        assert len(audit_entries) >= 1
        entry = audit_entries[-1]
        assert entry.outcome == "success"
    finally:
        session.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_audit_log_voucher_creation(async_client: "AsyncClient") -> None:
    """Verify voucher creation is audited."""
    # GIVEN: Authenticated admin
    session = next(get_session())
    try:
        admin = AdminUser(
            username="audit_voucher_admin",
            password_hash=hash_password("test_password"),
            email="audit_voucher_admin@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Admin creates a voucher
    client = async_client
    # Login
    await client.post(
        "/admin/login",
        data={"username": "audit_voucher_admin", "password": "test_password"},
    )

    # Create voucher
    expires = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    response = await client.post(
        "/admin/vouchers",
        json={
            "code": "AUDITVCH01",
            "device_limit": 5,
            "expires_utc": expires,
        },
    )
    assert response.status_code == 201

    # THEN: Audit log contains voucher creation
    session = next(get_session())
    try:
        audit_entries = session.exec(
            select(AuditLog).where(
                AuditLog.action.like("%voucher%")  # type: ignore[attr-defined]
            )
        ).all()
        assert len(audit_entries) >= 1
        entry = audit_entries[-1]
        assert entry.target_type in ["voucher", "Voucher"]
        assert entry.outcome == "success"
    finally:
        session.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_audit_log_required_fields(async_client: "AsyncClient") -> None:
    """Verify all audit log entries have required fields populated."""
    # GIVEN: Some audited operation
    session = next(get_session())
    try:
        admin = AdminUser(
            username="audit_fields_test",
            password_hash=hash_password("test_password"),
            email="audit_fields_test@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Performing audited action
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "audit_fields_test", "password": "test_password"},
    )

    # THEN: All required fields are populated
    session = next(get_session())
    try:
        recent_entries = session.exec(
            select(AuditLog).where(AuditLog.actor == "audit_fields_test").limit(1)
        ).all()
        assert len(recent_entries) >= 1

        entry = recent_entries[0]
        # Required fields from audit log model
        assert entry.actor is not None and entry.actor != ""
        assert entry.action is not None and entry.action != ""
        assert entry.outcome is not None and entry.outcome != ""
        assert entry.timestamp_utc is not None
    finally:
        session.close()
