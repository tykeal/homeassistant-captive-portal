# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Voucher purge service for automatic and manual cleanup of terminal vouchers.

Handles both automatic (retention-based) and manual (admin-initiated)
purge operations, including grant reference cleanup and audit logging.
"""

import logging
from datetime import datetime, timedelta, timezone

from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.services.audit_service import AuditService

logger = logging.getLogger("captive_portal")


class VoucherPurgeService:
    """Service for purging expired and revoked vouchers.

    Handles both automatic (retention-based) and manual (admin-initiated)
    purge operations, including grant reference cleanup and audit logging.

    Attributes:
        voucher_repo: Voucher repository for purge queries and deletion.
        grant_repo: Access grant repository for nullifying voucher references.
        audit_service: Audit logging service for recording purge operations.
        retention_days: Default retention period for auto-purge (30 days).
    """

    def __init__(
        self,
        voucher_repo: VoucherRepository,
        grant_repo: AccessGrantRepository,
        audit_service: AuditService,
        retention_days: int = 30,
    ) -> None:
        """Initialize voucher purge service.

        Args:
            voucher_repo: Voucher repository instance.
            grant_repo: Access grant repository instance.
            audit_service: Audit logging service instance.
            retention_days: Default retention period in days for auto-purge.
        """
        self.voucher_repo = voucher_repo
        self.grant_repo = grant_repo
        self.audit_service = audit_service
        self.retention_days = retention_days

    async def auto_purge(self) -> int:
        """Run automatic purge of vouchers past the retention period.

        Calculates the cutoff datetime based on the configured
        ``retention_days``, identifies purgeable voucher codes,
        nullifies associated grant references, deletes the vouchers,
        and logs an audit entry (only when vouchers were actually purged).

        Returns:
            Number of vouchers purged.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        codes = self.voucher_repo.get_purgeable_codes(cutoff)

        if not codes:
            return 0

        self.grant_repo.nullify_voucher_references(codes)
        purged_count = self.voucher_repo.purge(cutoff)
        self.voucher_repo.commit()

        if purged_count > 0:
            await self.audit_service.log(
                actor="system",
                action="voucher.auto_purge",
                outcome="success",
                target_type="voucher",
                meta={
                    "purged_count": purged_count,
                    "retention_days": self.retention_days,
                    "cutoff_utc": cutoff.isoformat(),
                },
            )
            logger.info(
                "Auto-purged %d terminal vouchers older than %d days.",
                purged_count,
                self.retention_days,
            )

        return purged_count

    async def count_purgeable(self, min_age_days: int) -> int:
        """Count vouchers eligible for manual purge with given age threshold.

        Args:
            min_age_days: Minimum age in days. 0 means all terminal vouchers.

        Returns:
            Count of eligible vouchers.
        """
        if min_age_days == 0:
            # Use a future cutoff to capture all terminal vouchers
            cutoff = datetime.now(timezone.utc) + timedelta(days=1)
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
        return self.voucher_repo.count_purgeable(cutoff)

    async def manual_purge(self, min_age_days: int, actor: str) -> int:
        """Execute admin-initiated purge.

        Args:
            min_age_days: Minimum age in days. 0 means all terminal vouchers.
            actor: Admin username for audit trail.

        Returns:
            Number of vouchers purged.
        """
        if min_age_days == 0:
            cutoff = datetime.now(timezone.utc) + timedelta(days=1)
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)

        codes = self.voucher_repo.get_purgeable_codes(cutoff)

        if not codes:
            return 0

        self.grant_repo.nullify_voucher_references(codes)
        purged_count = self.voucher_repo.purge(cutoff)
        self.voucher_repo.commit()

        if purged_count > 0:
            await self.audit_service.log(
                actor=actor,
                action="voucher.manual_purge",
                outcome="success",
                target_type="voucher",
                meta={
                    "purged_count": purged_count,
                    "min_age_days": min_age_days,
                    "cutoff_utc": cutoff.isoformat(),
                },
            )
            logger.info(
                "Manual purge by %s: purged %d terminal vouchers older than %d days.",
                actor,
                purged_count,
                min_age_days,
            )

        return purged_count
