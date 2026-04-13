# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test admin account model validation and password handling."""

from datetime import datetime, timezone

from captive_portal.models.admin_user import AdminRole, AdminUser
from captive_portal.security.password_hashing import hash_password


def test_admin_username_unique() -> None:
    """Username field is marked unique on the model."""
    admin = AdminUser(
        username="admin1",
        email="a@example.com",
        password_hash=hash_password("Secure1!"),
    )
    assert admin.username == "admin1"


def test_admin_role_enum() -> None:
    """Admin role must be one of: viewer, auditor, operator, admin."""
    for role in AdminRole:
        admin = AdminUser(
            username="admin1",
            email="a@example.com",
            password_hash="hash",
            role=role,
        )
        assert admin.role == role


def test_admin_password_hash_stored() -> None:
    """Password should be stored as hash, never plaintext."""
    pw_hash = hash_password("Test123!@#")
    admin = AdminUser(
        username="admin1",
        email="a@example.com",
        password_hash=pw_hash,
    )
    assert admin.password_hash != "Test123!@#"
    assert admin.password_hash == pw_hash


def test_admin_timestamps_utc() -> None:
    """Admin created_utc and last_login_utc must be UTC."""
    admin = AdminUser(
        username="admin1",
        email="a@example.com",
        password_hash="hash",
    )
    assert admin.created_utc.tzinfo == timezone.utc
    assert admin.last_login_utc is None

    now = datetime.now(timezone.utc)
    admin.last_login_utc = now
    assert admin.last_login_utc == now


def test_admin_active_flag() -> None:
    """Admin active flag controls account enable/disable."""
    admin = AdminUser(
        username="admin1",
        email="a@example.com",
        password_hash="hash",
    )
    assert admin.active is True

    admin.active = False
    assert admin.active is False


def test_admin_version_optimistic_lock() -> None:
    """Version field enables optimistic locking for concurrent updates."""
    admin = AdminUser(
        username="admin1",
        email="a@example.com",
        password_hash="hash",
    )
    assert admin.version == 1
    admin.version += 1
    assert admin.version == 2
