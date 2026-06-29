# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for data-layer repository edge cases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.admin_user import AdminRole, AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig, IdentifierAttr
from captive_portal.models.rental_control_event import RentalControlEvent
from captive_portal.models.voucher import Voucher
from captive_portal.persistence.access_grant_repository import AccessGrantRepository
from captive_portal.persistence.admin_repositories import (
    AdminUserRepository,
    AuditLogRepository,
    HAIntegrationConfigRepository,
)
from captive_portal.persistence.rental_control_event_repository import (
    RentalControlEventRepository,
)
from captive_portal.persistence.voucher_repository import VoucherRepository


def _rental_event(
    *,
    integration_id: str = "rental-control",
    event_index: int = 1,
    slot_name: str = "Guest One",
) -> RentalControlEvent:
    """Create a rental event with stable timestamps."""
    start = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
    return RentalControlEvent(
        integration_id=integration_id,
        event_index=event_index,
        slot_name=slot_name,
        slot_code="1234",
        last_four="6789",
        start_utc=start,
        end_utc=start + timedelta(days=2),
        raw_attributes='{"source":"test"}',
    )


def test_admin_repositories_load_by_primary_and_unique_keys(db_session: Session) -> None:
    """Admin repositories return their model classes and query persisted rows."""
    user = AdminUser(
        username="repo-admin",
        email="admin@example.test",
        password_hash="argon2-hash",
        role=AdminRole.ADMIN,
    )
    audit = AuditLog(
        actor="repo-admin",
        role_snapshot="admin",
        action="voucher.create",
        target_type="voucher",
        target_id="CODE1234",
        outcome="success",
    )
    integration = HAIntegrationConfig(
        integration_id="rental-control-main",
        identifier_attr=IdentifierAttr.SLOT_NAME,
    )
    db_session.add(user)
    db_session.add(audit)
    db_session.add(integration)
    db_session.commit()

    user_repo = AdminUserRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    integration_repo = HAIntegrationConfigRepository(db_session)

    assert user_repo.get_model_class() is AdminUser
    assert audit_repo.get_model_class() is AuditLog
    assert integration_repo.get_model_class() is HAIntegrationConfig
    assert user_repo.get_by_id(user.id) == user
    assert user_repo.get_by_username("repo-admin") == user
    assert user_repo.get_by_username("missing") is None
    assert audit_repo.get_by_id(audit.id) == audit
    assert integration_repo.get_by_id(integration.id) == integration
    assert integration_repo.get_by_integration_id("rental-control-main") == integration
    assert integration_repo.get_by_integration_id("missing") is None


@pytest.mark.asyncio
async def test_rental_control_repository_inserts_and_updates_by_event_key(
    db_session: Session,
) -> None:
    """Rental events are inserted once and updated by integration/index key."""
    repo = RentalControlEventRepository(db_session)

    inserted = await repo.upsert(_rental_event())
    db_session.commit()

    replacement = _rental_event(slot_name="Guest Two")
    replacement.slot_code = "4321"
    replacement.last_four = "9876"
    replacement.raw_attributes = '{"source":"updated"}'
    updated = await repo.upsert(replacement)
    db_session.commit()

    assert repo.get_model_class() is RentalControlEvent
    assert inserted.id is not None
    assert updated.id == inserted.id
    assert updated.slot_name == "Guest Two"
    assert updated.slot_code == "4321"
    assert updated.last_four == "9876"
    assert updated.raw_attributes == '{"source":"updated"}'
    assert repo.get_by_id(updated.id) == updated


@pytest.mark.asyncio
async def test_rental_control_repository_deletes_events_older_than_cutoff(
    db_session: Session,
) -> None:
    """Deleting old rental events uses UTC-aware cutoffs and preserves new rows."""
    repo = RentalControlEventRepository(db_session)
    old_event = await repo.upsert(_rental_event(event_index=10))
    new_event = await repo.upsert(_rental_event(event_index=11))
    assert old_event.id is not None
    assert new_event.id is not None
    old_event_id = old_event.id
    new_event_id = new_event.id
    old_event.end_utc = datetime(2026, 1, 2, 10, 0)
    new_event.end_utc = datetime(2026, 1, 5, 10, 0)
    db_session.add(old_event)
    db_session.add(new_event)
    db_session.commit()

    deleted = await repo.delete_events_older_than(datetime(2026, 1, 3, 0, 0, tzinfo=timezone.utc))
    db_session.commit()

    assert deleted == 1
    assert repo.get_by_id(old_event_id) is None
    assert repo.get_by_id(new_event_id) is not None


def test_voucher_repository_model_lookup_and_booking_search(db_session: Session) -> None:
    """Voucher repository looks up primary keys and booking references."""
    vouchers = [
        Voucher.model_validate(
            {"code": "BOOKREF001", "duration_minutes": 60, "booking_ref": " BookingA "}
        ),
        Voucher.model_validate(
            {"code": "BOOKREF002", "duration_minutes": 60, "booking_ref": "BookingA"}
        ),
        Voucher.model_validate(
            {"code": "BOOKREF003", "duration_minutes": 60, "booking_ref": "BookingB"}
        ),
    ]
    db_session.add_all(vouchers)
    db_session.commit()

    repo = VoucherRepository(db_session)

    assert repo.get_model_class() is Voucher
    assert repo.get_by_code("BOOKREF001") == vouchers[0]
    assert repo.get_by_code("MISSING1") is None
    assert {voucher.code for voucher in repo.find_by_booking_ref("BookingA")} == {
        "BOOKREF001",
        "BOOKREF002",
    }
    assert repo.find_by_booking_ref(" BookingA ") == []


def test_access_grant_repository_reports_model_class(db_session: Session) -> None:
    """Access grant repository exposes its SQLModel class."""
    repo = AccessGrantRepository(db_session)

    assert repo.get_model_class().__name__ == "AccessGrant"
