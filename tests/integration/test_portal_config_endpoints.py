# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for portal configuration CRUD endpoints."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from captive_portal.models.admin_user import AdminUser
from captive_portal.persistence.database import get_session
from captive_portal.security.password_hashing import hash_password

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_portal_config_default(async_client: "AsyncClient") -> None:
    """Verify GET /admin/portal-config returns default configuration."""
    # GIVEN: Authenticated admin
    session = next(get_session())
    try:
        admin = AdminUser(
            username="config_test_admin",
            password_hash=hash_password("test_password"),
            email="config_test_admin@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Fetching portal config
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "config_test_admin", "password": "test_password"},
    )
    response = await client.get("/admin/portal-config")

    # THEN: Returns default configuration
    assert response.status_code == 200
    data = response.json()
    assert data["rate_limit_attempts"] == 5
    assert data["rate_limit_window_seconds"] == 60
    assert data["redirect_to_original_url"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_portal_config(async_client: "AsyncClient") -> None:
    """Verify PUT /admin/portal-config updates configuration."""
    # GIVEN: Authenticated admin
    session = next(get_session())
    try:
        admin = AdminUser(
            username="config_update_admin",
            password_hash=hash_password("test_password"),
            email="config_update_admin@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Updating portal config
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "config_update_admin", "password": "test_password"},
    )

    update_response = await client.put(
        "/admin/portal-config",
        json={
            "rate_limit_attempts": 10,
            "rate_limit_window_seconds": 120,
            "redirect_to_original_url": False,
        },
    )

    # THEN: Configuration is updated
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["rate_limit_attempts"] == 10
    assert data["rate_limit_window_seconds"] == 120
    assert data["redirect_to_original_url"] is False

    # AND: Verify persistence
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "config_update_admin", "password": "test_password"},
    )
    get_response = await client.get("/admin/portal-config")
    assert get_response.status_code == 200
    persisted = get_response.json()
    assert persisted["rate_limit_attempts"] == 10


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_portal_config_partial(async_client: "AsyncClient") -> None:
    """Verify partial updates to portal configuration."""
    # GIVEN: Authenticated admin
    session = next(get_session())
    try:
        admin = AdminUser(
            username="config_partial_admin",
            password_hash=hash_password("test_password"),
            email="config_partial_admin@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Updating only some fields
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "config_partial_admin", "password": "test_password"},
    )

    # Update only grace period
    update_response = await client.put(
        "/admin/portal-config",
        json={"redirect_to_original_url": False},
    )

    # THEN: Only specified field is updated
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["redirect_to_original_url"] is False
    # Other fields retain defaults
    assert data["rate_limit_attempts"] == 5


@pytest.mark.asyncio
@pytest.mark.integration
async def test_portal_config_requires_auth(async_client: "AsyncClient") -> None:
    """Verify portal config endpoints require authentication."""
    # WHEN: Accessing without auth
    client = async_client
    get_response = await client.get("/admin/portal-config")
    put_response = await client.put(
        "/admin/portal-config",
        json={"rate_limit_attempts": 10},
    )

    # THEN: Requests are rejected
    assert get_response.status_code in (401, 403)
    assert put_response.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_portal_config_viewer_cannot_update(async_client: "AsyncClient") -> None:
    """Verify viewer role cannot update portal configuration."""
    # GIVEN: Authenticated viewer
    session = next(get_session())
    try:
        viewer = AdminUser(
            username="config_viewer",
            password_hash=hash_password("test_password"),
            email="config_viewer@test.local",
            role="viewer",
            created_utc=datetime.now(UTC),
        )
        session.add(viewer)
        session.commit()
    finally:
        session.close()

    # WHEN: Attempting to update config as viewer
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "config_viewer", "password": "test_password"},
    )
    response = await client.put(
        "/admin/portal-config",
        json={"rate_limit_attempts": 10},
    )

    # THEN: Request is forbidden
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.integration
async def test_portal_config_operator_can_view_not_update(async_client: "AsyncClient") -> None:
    """Verify operator role can view but not update portal configuration."""
    # GIVEN: Authenticated operator
    session = next(get_session())
    try:
        operator = AdminUser(
            username="config_operator",
            password_hash=hash_password("test_password"),
            email="config_operator@test.local",
            role="operator",
            created_utc=datetime.now(UTC),
        )
        session.add(operator)
        session.commit()
    finally:
        session.close()

    # WHEN: Viewing and attempting to update
    client = async_client
    await client.post(
        "/admin/login",
        data={"username": "config_operator", "password": "test_password"},
    )

    get_response = await client.get("/admin/portal-config")
    put_response = await client.put(
        "/admin/portal-config",
        json={"rate_limit_attempts": 10},
    )

    # THEN: View succeeds, update is forbidden
    assert get_response.status_code == 200
    assert put_response.status_code == 403
