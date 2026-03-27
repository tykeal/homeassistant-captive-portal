# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for save_integration with dropdown selection (T022).

Tests:
  (a) save accepts integration_id from dropdown selection and creates
      HAIntegrationConfig
  (b) save accepts integration_id from manual text input
  (c) 409 Conflict guard when auto-detected integration_id is already
      configured
  (d) form submits identifier_attr (field renamed) and it persists
      correctly
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


# ── (a) Dropdown selection ───────────────────────────────────────────


class TestSaveFromDropdown:
    """POST /admin/integrations/save accepts dropdown-selected integration_id."""

    def test_save_creates_config_from_dropdown_entity_id(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Selecting a discovered entity_id from the dropdown creates a row."""
        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "calendar.rental_control_cabin_a",
                "identifier_attr": "slot_code",
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303, f"Expected redirect, got {resp.status_code}"

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "calendar.rental_control_cabin_a"
            )
        ).first()

        assert row is not None, "Integration was not persisted"
        assert row.integration_id == "calendar.rental_control_cabin_a"
        assert row.identifier_attr == IdentifierAttr.SLOT_CODE
        assert row.checkout_grace_minutes == 15


# ── (b) Manual text input ───────────────────────────────────────────


class TestSaveFromManualInput:
    """POST /admin/integrations/save accepts manual text integration_id."""

    def test_save_creates_config_from_manual_input(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Typing a custom integration_id in the text input creates a row."""
        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "calendar.rental_control_custom_unit",
                "identifier_attr": "slot_name",
                "checkout_grace_minutes": "20",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "calendar.rental_control_custom_unit"
            )
        ).first()

        assert row is not None, "Integration was not persisted"
        assert row.identifier_attr == IdentifierAttr.SLOT_NAME
        assert row.checkout_grace_minutes == 20


# ── (c) 409 Conflict guard ──────────────────────────────────────────


class TestSaveDuplicateConflict:
    """Creating with a duplicate integration_id returns 409 Conflict."""

    def test_duplicate_integration_id_returns_409(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Second create with same integration_id redirects with error."""
        # Seed an existing integration
        existing = HAIntegrationConfig(
            integration_id="calendar.rental_control_dup_test",
            identifier_attr=IdentifierAttr.SLOT_CODE,
            checkout_grace_minutes=15,
        )
        db_session.add(existing)
        db_session.commit()

        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "calendar.rental_control_dup_test",
                "identifier_attr": "slot_code",
                "checkout_grace_minutes": "15",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303, f"Expected 303 redirect, got {resp.status_code}"
        assert "error=Integration+already+exists" in resp.headers["location"]


# ── (d) identifier_attr field renamed ───────────────────────────────


class TestIdentifierAttrFieldRenamed:
    """Form submits identifier_attr (not auth_attribute) and it persists."""

    @pytest.mark.parametrize(
        "attr_value, expected",
        [
            ("slot_code", IdentifierAttr.SLOT_CODE),
            ("slot_name", IdentifierAttr.SLOT_NAME),
            ("last_four", IdentifierAttr.LAST_FOUR),
        ],
        ids=["slot_code", "slot_name", "last_four"],
    )
    def test_identifier_attr_persists_correctly(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
        attr_value: str,
        expected: IdentifierAttr,
    ) -> None:
        """identifier_attr form field value is stored as IdentifierAttr enum."""
        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": f"calendar.rental_control_attr_{attr_value}",
                "identifier_attr": attr_value,
                "checkout_grace_minutes": "10",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == f"calendar.rental_control_attr_{attr_value}"
            )
        ).first()

        assert row is not None
        assert row.identifier_attr == expected
        assert isinstance(row.identifier_attr, IdentifierAttr)

    def test_legacy_auth_attribute_still_works(
        self,
        client: TestClient,
        admin_user: Any,
        db_session: Session,
    ) -> None:
        """Legacy auth_attribute form field is accepted for backward compat."""
        csrf = _login(client)

        resp = client.post(
            "/admin/integrations/save",
            data={
                "integration_id": "calendar.rental_control_legacy_test",
                "auth_attribute": "last_four",
                "checkout_grace_minutes": "5",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        db_session.expire_all()
        row = db_session.exec(
            select(HAIntegrationConfig).where(
                HAIntegrationConfig.integration_id == "calendar.rental_control_legacy_test"
            )
        ).first()

        assert row is not None
        assert row.identifier_attr == IdentifierAttr.LAST_FOUR
