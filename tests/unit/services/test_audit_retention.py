# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for audit log retention service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from typing import Generator

import pytest
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from captive_portal.models.audit_config import AuditConfig
from captive_portal.models.audit_log import AuditLog
from captive_portal.services.audit_cleanup_service import AuditCleanupService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create in-memory database session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_cleanup_expired_logs_default_retention(db_session: Session) -> None:
    """Test cleanup with default 30-day retention."""
    config = AuditConfig()  # Default 30 days
    service = AuditCleanupService(db_session, config)

    # Create logs at different ages
    now = datetime.now(timezone.utc)
    old_log = AuditLog(
        actor="admin",
        action="test.action",
        timestamp_utc=now - timedelta(days=31),
        outcome="success",
    )
    recent_log = AuditLog(
        actor="admin",
        action="test.action",
        timestamp_utc=now - timedelta(days=29),
        outcome="success",
    )

    db_session.add(old_log)
    db_session.add(recent_log)
    db_session.commit()

    # Cleanup should remove old log only
    deleted = service.cleanup_expired_logs()
    assert deleted == 1

    # Verify only recent log remains
    from sqlmodel import select

    remaining = list(db_session.exec(select(AuditLog)))
    assert len(remaining) == 1
    assert remaining[0].id == recent_log.id


def test_cleanup_expired_logs_custom_retention(db_session: Session) -> None:
    """Test cleanup with custom retention period."""
    config = AuditConfig(audit_retention_days=7)
    service = AuditCleanupService(db_session, config)

    now = datetime.now(timezone.utc)
    old_log = AuditLog(
        actor="admin",
        action="test.action",
        timestamp_utc=now - timedelta(days=8),
        outcome="success",
    )
    recent_log = AuditLog(
        actor="admin",
        action="test.action",
        timestamp_utc=now - timedelta(days=6),
        outcome="success",
    )

    db_session.add(old_log)
    db_session.add(recent_log)
    db_session.commit()

    deleted = service.cleanup_expired_logs()
    assert deleted == 1


def test_cleanup_no_expired_logs(db_session: Session) -> None:
    """Test cleanup when no logs are expired."""
    config = AuditConfig(audit_retention_days=30)
    service = AuditCleanupService(db_session, config)

    # Create only recent logs
    now = datetime.now(timezone.utc)
    for i in range(5):
        log = AuditLog(
            actor="admin",
            action=f"test.action{i}",
            timestamp_utc=now - timedelta(days=i),
            outcome="success",
        )
        db_session.add(log)
    db_session.commit()

    # No logs should be deleted
    deleted = service.cleanup_expired_logs()
    assert deleted == 0

    # All logs should remain
    from sqlmodel import select

    remaining = list(db_session.exec(select(AuditLog)))
    assert len(remaining) == 5


def test_cleanup_all_expired_logs(db_session: Session) -> None:
    """Test cleanup when all logs are expired."""
    config = AuditConfig(audit_retention_days=30)
    service = AuditCleanupService(db_session, config)

    # Create only old logs
    now = datetime.now(timezone.utc)
    for i in range(5):
        log = AuditLog(
            actor="admin",
            action=f"test.action{i}",
            timestamp_utc=now - timedelta(days=31 + i),
            outcome="success",
        )
        db_session.add(log)
    db_session.commit()

    # All logs should be deleted
    deleted = service.cleanup_expired_logs()
    assert deleted == 5

    # No logs should remain
    from sqlmodel import select

    remaining = list(db_session.exec(select(AuditLog)))
    assert len(remaining) == 0


def test_audit_config_validation() -> None:
    """Test audit config validation constraints."""
    # Valid config
    config = AuditConfig(audit_retention_days=30)
    assert config.audit_retention_days == 30

    # Test minimum
    config = AuditConfig(audit_retention_days=1)
    assert config.audit_retention_days == 1

    # Test maximum
    config = AuditConfig(audit_retention_days=90)
    assert config.audit_retention_days == 90

    # Test invalid (too low)
    with pytest.raises(ValueError):
        AuditConfig(audit_retention_days=0)

    # Test invalid (too high)
    with pytest.raises(ValueError):
        AuditConfig(audit_retention_days=91)
