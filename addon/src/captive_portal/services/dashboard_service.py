# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Dashboard service for aggregated statistics and recent activity."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, func, select
from sqlalchemy import desc

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.models.admin_user import AdminUser
from captive_portal.models.audit_log import AuditLog
from captive_portal.models.ha_integration_config import HAIntegrationConfig
from captive_portal.models.voucher import Voucher, VoucherStatus

logger = logging.getLogger("captive_portal")


@dataclass
class DashboardStats:
    """Aggregated statistics for the dashboard cards.

    Attributes:
        active_grants: Count of currently active grants.
        pending_grants: Count of pending (future) grants.
        available_vouchers: Count of unused, non-expired vouchers.
        integrations: Count of configured HA integrations.
    """

    active_grants: int
    pending_grants: int
    available_vouchers: int
    integrations: int


@dataclass
class ActivityLogEntry:
    """Enriched audit log entry for dashboard display.

    Attributes:
        timestamp: Action timestamp (UTC).
        action: Action type string.
        target_type: Entity type affected.
        target_id: Entity identifier affected.
        admin_username: Resolved admin username or raw actor.
    """

    timestamp: datetime
    action: str
    target_type: str
    target_id: str
    admin_username: str


class DashboardService:
    """Aggregates dashboard statistics and recent activity.

    Args:
        session: Active database session.
    """

    def __init__(self, session: Session) -> None:
        """Initialise dashboard service with database session.

        Args:
            session: Active database session for queries.
        """
        self._session = session

    def get_stats(self, current_time: Optional[datetime] = None) -> DashboardStats:
        """Compute aggregated dashboard statistics.

        Counts are computed in real-time from the database. Grant status
        is determined by comparing timestamps against ``current_time``
        rather than relying on the stored ``status`` field (which may be
        stale), except for revoked grants which are always excluded.

        Args:
            current_time: Override for current UTC time (for testing).

        Returns:
            DashboardStats with all four counts.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Active grants: not revoked, started, not yet ended
        active_count: int = self._session.exec(
            select(func.count())
            .select_from(AccessGrant)
            .where(
                AccessGrant.status != GrantStatus.REVOKED,
                AccessGrant.start_utc <= current_time,
                AccessGrant.end_utc > current_time,
            )
        ).one()

        # Pending grants: not revoked, not yet started
        pending_count: int = self._session.exec(
            select(func.count())
            .select_from(AccessGrant)
            .where(
                AccessGrant.status != GrantStatus.REVOKED,
                AccessGrant.start_utc > current_time,
            )
        ).one()

        # Available vouchers: unused and not expired
        # Voucher.expires_utc is a computed property, not a DB column,
        # so we compute expiry in Python after fetching all unused vouchers
        all_unused = self._session.exec(
            select(Voucher).where(Voucher.status == VoucherStatus.UNUSED)
        ).all()
        available_count = 0
        for v in all_unused:
            expires = v.expires_utc
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > current_time:
                available_count += 1

        # Integrations count
        integrations_count: int = self._session.exec(
            select(func.count()).select_from(HAIntegrationConfig)
        ).one()

        return DashboardStats(
            active_grants=active_count,
            pending_grants=pending_count,
            available_vouchers=available_count,
            integrations=integrations_count,
        )

    def get_recent_activity(self, limit: int = 20) -> list[ActivityLogEntry]:
        """Fetch recent audit log entries with admin username resolution.

        Joins ``AuditLog`` with ``AdminUser`` to resolve actor UUIDs to
        display usernames. Falls back to the raw ``actor`` string when
        no matching admin user is found.

        Args:
            limit: Maximum number of entries to return (default 20).

        Returns:
            List of ActivityLogEntry ordered by timestamp descending.
        """
        logs = self._session.exec(
            select(AuditLog)
            .order_by(desc(AuditLog.timestamp_utc))  # type: ignore[arg-type]
            .limit(limit)
        ).all()

        # Build admin username lookup
        admin_ids: set[str] = {log.actor for log in logs}
        admin_map: dict[str, str] = {}
        for actor_str in admin_ids:
            try:
                from uuid import UUID

                actor_uuid = UUID(actor_str)
                admin = self._session.exec(
                    select(AdminUser).where(AdminUser.id == actor_uuid)
                ).first()
                if admin:
                    admin_map[actor_str] = admin.username
            except (ValueError, AttributeError):
                # Not a UUID — use raw string (system actions, etc.)
                pass

        entries: list[ActivityLogEntry] = []
        for log in logs:
            entries.append(
                ActivityLogEntry(
                    timestamp=log.timestamp_utc,
                    action=log.action,
                    target_type=log.target_type or "",
                    target_id=log.target_id or "",
                    admin_username=admin_map.get(log.actor, log.actor),
                )
            )

        return entries
