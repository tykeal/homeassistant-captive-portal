# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for save_integration identifier_attr handling (T014).

The ``save_integration`` POST handler receives ``auth_attribute`` from
the HTML form and must convert it to an ``IdentifierAttr`` enum value,
assigning it to the model's ``identifier_attr`` field.

A previous version had a bug where it assigned to ``auth_attribute``
(which does not exist on the model) instead of ``identifier_attr``.
These tests prevent that regression from reoccurring.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from captive_portal.models.ha_integration_config import (
    HAIntegrationConfig,
    IdentifierAttr,
)


def _login(client: TestClient) -> str:
    """Authenticate as admin and return the CSRF token."""
    resp = client.post(
        "/api/admin/auth/login",
        json={"username": "testadmin", "password": "SecureP@ss123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    csrf_token: str = resp.json()["csrf_token"]
    client.cookies.set("csrftoken", csrf_token)
    return csrf_token


# ── Create path ──────────────────────────────────────────────────────


class TestCreateIntegrationIdentifierAttr:
    """POST /admin/integrations/save (create) must store identifier_attr."""

    @pytest.mark.parametrize(
        "form_value, expected",
        [
            ("slot_name", IdentifierAttr.SLOT_NAME),
            ("last_four", IdentifierAttr.LAST_FOUR),
        ],
        ids=["slot_name", "last_four"],
    )
    def test_create_sets_identifier_attr(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
        form_value: str,
        expected: IdentifierAttr,
    ) -> None:
        """Creating an integration must persist the chosen identifier_attr."""
        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": f"rental_control_{form_value}",
                "auth_attribute": form_value,
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        # The endpoint should redirect on success
        assert resp.status_code == 303, f"Expected redirect, got {resp.status_code}"

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == f"rental_control_{form_value}"
            )
        ).first()

        assert row is not None, "Integration was not persisted to the database"
        assert row.identifier_attr == expected, (
            f"Expected identifier_attr={expected!r}, got {row.identifier_attr!r}"
        )

    def test_create_slot_code_sets_identifier_attr(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Explicit slot_code test — verifies the field, not just default."""
        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "rental_control_explicit_sc",
                "auth_attribute": "slot_code",
                "checkout_grace_minutes": "10",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "rental_control_explicit_sc"
            )
        ).first()

        assert row is not None
        assert row.identifier_attr == IdentifierAttr.SLOT_CODE
        # Confirm the model has no stray ``auth_attribute`` column
        assert not hasattr(row, "auth_attribute") or (
            getattr(row, "auth_attribute", None) is None
        ), "Model should not have an auth_attribute field"


# ── Update path ──────────────────────────────────────────────────────


class TestUpdateIntegrationIdentifierAttr:
    """POST /admin/integrations/save (update) must change identifier_attr."""

    @pytest.mark.parametrize(
        "target_value, expected",
        [
            ("slot_name", IdentifierAttr.SLOT_NAME),
            ("last_four", IdentifierAttr.LAST_FOUR),
            ("slot_code", IdentifierAttr.SLOT_CODE),
        ],
        ids=["to_slot_name", "to_last_four", "to_slot_code"],
    )
    def test_update_changes_identifier_attr(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
        target_value: str,
        expected: IdentifierAttr,
    ) -> None:
        """Updating an integration must change identifier_attr correctly."""
        # Seed with a DIFFERENT starting value to detect a real change
        initial = (
            IdentifierAttr.SLOT_CODE if target_value != "slot_code" else IdentifierAttr.SLOT_NAME
        )
        config = HAIntegrationConfig(
            integration_id=f"rental_control_upd_{target_value}",
            identifier_attr=initial,
            checkout_grace_minutes=10,
        )
        db_session.add(config)
        db_session.commit()
        db_session.refresh(config)
        config_id = config.id

        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "id": str(config_id),
                "integration_id": f"rental_control_upd_{target_value}",
                "auth_attribute": target_value,
                "checkout_grace_minutes": "20",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        updated = db_session.get(HAIntegrationConfig, config_id)

        assert updated is not None
        assert updated.identifier_attr == expected, (
            f"Expected identifier_attr={expected!r}, got {updated.identifier_attr!r}"
        )
        assert updated.checkout_grace_minutes == 20

    def test_update_identifier_attr_uses_enum_not_raw_string(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """After update, identifier_attr must be an IdentifierAttr enum."""
        config = HAIntegrationConfig(
            integration_id="rental_control_enum_check",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        db_session.add(config)
        db_session.commit()
        db_session.refresh(config)
        config_id = config.id

        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "id": str(config_id),
                "integration_id": "rental_control_enum_check",
                "auth_attribute": "last_four",
                "checkout_grace_minutes": "5",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        updated = db_session.get(HAIntegrationConfig, config_id)

        assert updated is not None
        assert isinstance(updated.identifier_attr, IdentifierAttr), (
            f"identifier_attr should be IdentifierAttr, got {type(updated.identifier_attr)}"
        )
        assert updated.identifier_attr is IdentifierAttr.LAST_FOUR
