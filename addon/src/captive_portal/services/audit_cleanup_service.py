# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Audit log cleanup service for retention policy enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlmodel import Session

from captive_portal.models.audit_config import AuditConfig
from captive_portal.models.audit_log import AuditLog


class AuditCleanupService:
    """Service for cleaning up expired audit logs based on retention policy."""

    def __init__(self, db: Session, config: AuditConfig):
        """Initialize audit cleanup service.

        Args:
            db: Database session
            config: Audit configuration with retention policy
        """
        self.db = db
        self.config = config

    def cleanup_expired_logs(self) -> int:
        """Delete audit logs older than retention period.

        Returns:
            Number of deleted records
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.audit_retention_days)

        # Delete logs older than retention period
        stmt = delete(AuditLog).where(
            AuditLog.timestamp_utc < cutoff  # type: ignore[arg-type]
        )
        result = self.db.exec(stmt)
        self.db.commit()

        return result.rowcount or 0
