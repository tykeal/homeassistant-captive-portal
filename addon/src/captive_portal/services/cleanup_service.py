# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Cleanup service for expired Rental Control events."""

import logging
from datetime import datetime, timedelta, timezone

from captive_portal.persistence.repositories import RentalControlEventRepository
from captive_portal.services.audit_service import AuditService

logger = logging.getLogger(__name__)

DEFAULT_EVENT_RETENTION_DAYS = 1


def build_event_retention_cutoff(
    retention_days: int = DEFAULT_EVENT_RETENTION_DAYS,
) -> datetime:
    """Return the shared cutoff used for expired Rental Control events.

    Args:
        retention_days: Number of full days to retain events after checkout

    Returns:
        UTC cutoff datetime for deleting stale events
    """
    return datetime.now(timezone.utc) - timedelta(days=retention_days)


class CleanupService:
    """Service for cleaning up expired Rental Control events.

    Attributes:
        event_repo: Event repository
        audit_service: Audit logging service
        retention_days: Number of days to retain events post-checkout
    """

    def __init__(
        self,
        event_repo: RentalControlEventRepository,
        audit_service: AuditService,
        retention_days: int = DEFAULT_EVENT_RETENTION_DAYS,
    ) -> None:
        """Initialize cleanup service.

        Args:
            event_repo: Event repository
            audit_service: Audit logging service
            retention_days: Retention period in days (default 1)
        """
        self.event_repo = event_repo
        self.audit_service = audit_service
        self.retention_days = retention_days

    async def cleanup_expired_events(self) -> int:
        """Delete events older than retention period.

        Returns:
            Number of deleted events

        Raises:
            Exception: On database errors
        """
        cutoff_date = build_event_retention_cutoff(self.retention_days)

        logger.info(
            "Starting event cleanup",
            extra={
                "cutoff_date": cutoff_date.isoformat(),
                "retention_days": self.retention_days,
            },
        )

        deleted_count = await self.event_repo.delete_events_older_than(cutoff_date)

        # Log audit event
        await self.audit_service.log(
            actor="system",
            action="event.cleanup",
            outcome="success",
            meta={"deleted_count": deleted_count, "cutoff_date": cutoff_date.isoformat()},
        )

        logger.info(
            "Event cleanup completed",
            extra={"deleted_count": deleted_count},
        )

        return deleted_count
