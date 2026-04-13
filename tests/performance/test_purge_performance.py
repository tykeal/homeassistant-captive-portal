# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Performance test for batch voucher purge (SC-003).

T022a: Verifies that batch purge of 10,000 terminal vouchers
completes within 10 seconds.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.voucher import Voucher, VoucherStatus
from captive_portal.persistence.repositories import (
    AccessGrantRepository,
    VoucherRepository,
)
from captive_portal.services.audit_service import AuditService
from captive_portal.services.voucher_purge_service import VoucherPurgeService


@pytest.mark.performance
class TestPurgePerformance:
    """SC-003: Batch purge performance tests."""

    @pytest.mark.asyncio
    async def test_purge_10000_vouchers_under_10_seconds(self, db_session: Session) -> None:
        """Batch purge of 10,000 terminal vouchers completes within 10 seconds."""
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        batch_size = 10_000

        # Bulk-insert 10,000 expired vouchers
        vouchers = []
        for i in range(batch_size):
            code = f"PERF{i:06d}"
            v = Voucher(
                code=code,
                duration_minutes=60,
                status=VoucherStatus.EXPIRED,
                status_changed_utc=old_time,
            )
            vouchers.append(v)

        db_session.add_all(vouchers)
        db_session.commit()

        # Verify all were inserted
        repo = VoucherRepository(db_session)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        count = repo.count_purgeable(cutoff)
        assert count == batch_size

        # Measure purge time
        service = VoucherPurgeService(
            voucher_repo=repo,
            grant_repo=AccessGrantRepository(db_session),
            audit_service=AuditService(db_session),
        )

        start = time.monotonic()
        purged = await service.auto_purge()
        elapsed = time.monotonic() - start

        assert purged == batch_size
        assert elapsed < 10.0, f"Purge took {elapsed:.2f}s, expected < 10s"

        # Verify all purged
        remaining = repo.count_purgeable(cutoff)
        assert remaining == 0
