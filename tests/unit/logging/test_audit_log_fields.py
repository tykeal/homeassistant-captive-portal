# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0711 – Unit tests for audit service required fields.

Validates that AuditService.log() emits entries containing every
required field: user (actor), action, resource (target_type),
result (outcome), and correlation_id (the entry UUID).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlmodel import Session, select

from captive_portal.models.audit_log import AuditLog
from captive_portal.services.audit_service import AuditService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_audit_entries(session: Session) -> list[AuditLog]:
    """Return all audit log entries in the session."""
    stmt: Any = select(AuditLog)
    return list(session.exec(stmt).all())


# ---------------------------------------------------------------------------
# Core field presence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_entry_has_actor(db_session: Session) -> None:
    """Audit entry must record the actor (user) who performed the action."""
    svc = AuditService(db_session)
    entry = await svc.log(actor="admin_jane", action="grant.create", outcome="success")
    assert entry.actor == "admin_jane"


@pytest.mark.asyncio
async def test_log_entry_has_action(db_session: Session) -> None:
    """Audit entry must record the action identifier."""
    svc = AuditService(db_session)
    entry = await svc.log(actor="admin", action="voucher.create", outcome="success")
    assert entry.action == "voucher.create"


@pytest.mark.asyncio
async def test_log_entry_has_outcome(db_session: Session) -> None:
    """Audit entry must record the result / outcome."""
    svc = AuditService(db_session)
    entry = await svc.log(actor="admin", action="grant.revoke", outcome="denied")
    assert entry.outcome == "denied"


@pytest.mark.asyncio
async def test_log_entry_has_target_type(db_session: Session) -> None:
    """Audit entry must support a resource / target_type field."""
    svc = AuditService(db_session)
    entry = await svc.log(
        actor="admin",
        action="voucher.create",
        outcome="success",
        target_type="voucher",
    )
    assert entry.target_type == "voucher"


@pytest.mark.asyncio
async def test_log_entry_has_target_id(db_session: Session) -> None:
    """Audit entry must support a target_id (resource identifier)."""
    svc = AuditService(db_session)
    entry = await svc.log(
        actor="admin",
        action="grant.revoke",
        outcome="success",
        target_type="grant",
        target_id="abc-123",
    )
    assert entry.target_id == "abc-123"


@pytest.mark.asyncio
async def test_log_entry_has_correlation_id(db_session: Session) -> None:
    """Every audit entry receives a unique UUID as correlation_id."""
    svc = AuditService(db_session)
    entry = await svc.log(actor="system", action="cleanup", outcome="success")
    assert entry.id is not None
    assert isinstance(entry.id, UUID)


@pytest.mark.asyncio
async def test_log_entry_has_timestamp(db_session: Session) -> None:
    """Every audit entry must have a UTC timestamp."""
    svc = AuditService(db_session)
    entry = await svc.log(actor="admin", action="login", outcome="success")
    assert entry.timestamp_utc is not None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_entry_persisted_to_database(db_session: Session) -> None:
    """Audit entry is persisted to the database immediately."""
    svc = AuditService(db_session)
    entry = await svc.log(
        actor="admin",
        action="voucher.create",
        outcome="success",
        target_type="voucher",
        target_id="V-1234",
    )

    rows = _get_audit_entries(db_session)
    assert len(rows) >= 1
    persisted = next(r for r in rows if r.id == entry.id)
    assert persisted.actor == "admin"
    assert persisted.action == "voucher.create"
    assert persisted.outcome == "success"
    assert persisted.target_type == "voucher"
    assert persisted.target_id == "V-1234"


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_voucher_created_fields(db_session: Session) -> None:
    """log_voucher_created fills actor, action, outcome, target fields."""
    svc = AuditService(db_session)
    entry = await svc.log_voucher_created(
        actor="admin",
        role="admin",
        voucher_code="V-TEST",
        duration_minutes=60,
    )
    assert entry.actor == "admin"
    assert entry.action == "voucher.create"
    assert entry.outcome == "success"
    assert entry.target_type == "voucher"
    assert entry.target_id == "V-TEST"
    assert isinstance(entry.id, UUID)


@pytest.mark.asyncio
async def test_log_grant_revoked_fields(db_session: Session) -> None:
    """log_grant_revoked fills required fields."""
    from uuid import uuid4

    grant_id = uuid4()
    svc = AuditService(db_session)
    entry = await svc.log_grant_revoked(
        actor="admin",
        role="admin",
        grant_id=grant_id,
        reason="checkout",
    )
    assert entry.actor == "admin"
    assert entry.action == "grant.revoke"
    assert entry.outcome == "success"
    assert entry.target_type == "grant"
    assert entry.target_id == str(grant_id)


@pytest.mark.asyncio
async def test_log_rbac_denied_fields(db_session: Session) -> None:
    """log_rbac_denied fills required fields with 'denied' outcome."""
    svc = AuditService(db_session)
    entry = await svc.log_rbac_denied(
        actor="viewer_bob",
        role="viewer",
        action="grants.extend",
    )
    assert entry.actor == "viewer_bob"
    assert entry.outcome == "denied"
    assert isinstance(entry.id, UUID)


# ---------------------------------------------------------------------------
# Meta / extra data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_entry_meta_field(db_session: Session) -> None:
    """Audit entry supports arbitrary JSON metadata."""
    svc = AuditService(db_session)
    entry = await svc.log(
        actor="admin",
        action="grant.extend",
        outcome="success",
        meta={"ip": "10.0.0.1", "additional_minutes": 30},
    )
    assert entry.meta is not None
    assert entry.meta["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_multiple_entries_have_unique_ids(db_session: Session) -> None:
    """Each audit entry gets a distinct UUID."""
    svc = AuditService(db_session)
    e1 = await svc.log(actor="a", action="x", outcome="success")
    e2 = await svc.log(actor="b", action="y", outcome="success")
    assert e1.id != e2.id
