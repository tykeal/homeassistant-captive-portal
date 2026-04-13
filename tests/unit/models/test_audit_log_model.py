# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Test audit log model for administrative action tracking."""

from datetime import datetime, timezone

from captive_portal.models.audit_log import AuditLog


def test_audit_log_required_fields() -> None:
    """Audit log must capture actor, action, timestamp_utc, outcome."""
    log = AuditLog(
        actor="admin1",
        action="voucher.create",
        timestamp_utc=datetime.now(timezone.utc),
        outcome="success",
    )
    assert log.actor == "admin1"
    assert log.action == "voucher.create"
    assert log.timestamp_utc is not None
    assert log.outcome == "success"
    assert log.id is not None


def test_audit_log_timestamp_utc() -> None:
    """Audit log timestamp must be UTC with ISO 8601 format."""
    utc_now = datetime.now(timezone.utc)
    log = AuditLog(
        actor="admin1",
        action="voucher.create",
        timestamp_utc=utc_now,
        outcome="success",
    )
    assert log.timestamp_utc.tzinfo == timezone.utc
    assert log.timestamp_utc == utc_now


def test_audit_log_role_snapshot() -> None:
    """Role at time of action should be captured for historical context."""
    log = AuditLog(
        actor="admin1",
        role_snapshot="operator",
        action="voucher.create",
        outcome="success",
    )
    assert log.role_snapshot == "operator"

    log2 = AuditLog(
        actor="admin2",
        action="grant.revoke",
        outcome="success",
    )
    assert log2.role_snapshot is None


def test_audit_log_target_tracking() -> None:
    """Target entity type and ID should be recorded."""
    log = AuditLog(
        actor="admin1",
        action="voucher.create",
        target_type="voucher",
        target_id="ABC123",
        outcome="success",
    )
    assert log.target_type == "voucher"
    assert log.target_id == "ABC123"

    log2 = AuditLog(
        actor="admin1",
        action="system.startup",
        outcome="success",
    )
    assert log2.target_type is None
    assert log2.target_id is None


def test_audit_log_meta_json() -> None:
    """Meta field allows arbitrary JSON for additional context."""
    meta = {"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"}
    log = AuditLog(
        actor="admin1",
        action="voucher.create",
        outcome="success",
        meta=meta,
    )
    assert log.meta == meta
    assert log.meta["ip"] == "192.168.1.1"


def test_audit_log_immutable() -> None:
    """Audit logs are created with immutable timestamp."""
    utc_now = datetime.now(timezone.utc)
    log = AuditLog(
        actor="admin1",
        action="voucher.create",
        timestamp_utc=utc_now,
        outcome="success",
    )
    assert log.timestamp_utc == utc_now
