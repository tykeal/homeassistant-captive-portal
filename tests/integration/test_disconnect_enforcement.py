# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0716 – Integration tests for disconnect enforcement NFR.

Non-functional requirement: disconnect enforcement p95 < 30 s after access expiry.
Validates that the revocation/disconnect mechanism initiates within the timing bound
when a grant expires or is explicitly revoked.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from captive_portal.models.access_grant import AccessGrant, GrantStatus
from captive_portal.services.grant_service import GrantService
from captive_portal.utils.metrics import MetricsCollector


DISCONNECT_P95_LIMIT_SECONDS = 30.0


@pytest.fixture
def grant_service(db_session: Session) -> GrantService:
    """Create a GrantService backed by the test database."""
    return GrantService(session=db_session)


@pytest.fixture
def active_grant(db_session: Session) -> AccessGrant:
    """Insert an active grant that is about to expire."""
    now = datetime.now(timezone.utc)
    grant = AccessGrant(
        device_id="test-device-01",
        mac="AA:BB:CC:DD:EE:01",
        start_utc=now - timedelta(hours=1),
        end_utc=now + timedelta(seconds=5),
        status=GrantStatus.ACTIVE,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


@pytest.fixture
def expired_grant(db_session: Session) -> AccessGrant:
    """Insert a grant whose access has already expired."""
    now = datetime.now(timezone.utc)
    grant = AccessGrant(
        device_id="test-device-02",
        mac="AA:BB:CC:DD:EE:02",
        start_utc=now - timedelta(hours=2),
        end_utc=now - timedelta(seconds=10),
        status=GrantStatus.ACTIVE,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant


@pytest.mark.integration
class TestDisconnectEnforcementTiming:
    """Verify disconnect enforcement meets p95 < 30 s NFR."""

    @pytest.mark.asyncio
    async def test_revoke_completes_under_p95_limit(
        self, grant_service: GrantService, active_grant: AccessGrant
    ) -> None:
        """Single revoke operation completes well under 30 s."""
        start = time.monotonic()
        result = await grant_service.revoke(active_grant.id)
        elapsed = time.monotonic() - start

        assert result.status == GrantStatus.REVOKED
        assert elapsed < DISCONNECT_P95_LIMIT_SECONDS

    @pytest.mark.asyncio
    async def test_revoke_expired_grant_under_p95_limit(
        self, grant_service: GrantService, expired_grant: AccessGrant
    ) -> None:
        """Revoking an already-expired grant still completes quickly."""
        start = time.monotonic()
        result = await grant_service.revoke(expired_grant.id)
        elapsed = time.monotonic() - start

        assert result.status == GrantStatus.REVOKED
        assert elapsed < DISCONNECT_P95_LIMIT_SECONDS

    @pytest.mark.asyncio
    async def test_batch_revoke_p95_under_limit(self, db_session: Session) -> None:
        """Batch of 20 revocations: p95 latency must be < 30 s."""
        now = datetime.now(timezone.utc)
        grants: list[AccessGrant] = []
        for i in range(20):
            g = AccessGrant(
                device_id=f"test-device-batch-{i:02d}",
                mac=f"AA:BB:CC:DD:{i:02X}:FF",
                start_utc=now - timedelta(hours=1),
                end_utc=now - timedelta(seconds=1),
                status=GrantStatus.ACTIVE,
            )
            db_session.add(g)
            grants.append(g)
        db_session.commit()
        for g in grants:
            db_session.refresh(g)

        service = GrantService(session=db_session)
        latencies: list[float] = []
        for g in grants:
            start = time.monotonic()
            await service.revoke(g.id)
            latencies.append(time.monotonic() - start)

        latencies.sort()
        p95_idx = min(math.ceil(len(latencies) * 0.95) - 1, len(latencies) - 1)
        p95 = latencies[p95_idx]
        assert p95 < DISCONNECT_P95_LIMIT_SECONDS, (
            f"p95={p95:.3f}s exceeds {DISCONNECT_P95_LIMIT_SECONDS}s"
        )


@pytest.mark.integration
class TestDisconnectEnforcementMetrics:
    """Verify disconnect enforcement timing is within acceptable bounds."""

    @pytest.mark.asyncio
    async def test_revoke_latency_within_limit(
        self, grant_service: GrantService, active_grant: AccessGrant
    ) -> None:
        """Revoke call latency must be within NFR limit."""
        collector = MetricsCollector()
        with collector.time_operation("disconnect_enforcement_latency"):
            await grant_service.revoke(active_grant.id)

        stats = collector.get_histogram_stats("disconnect_enforcement_latency")
        assert stats["count"] == 1.0
        assert stats["max"] < DISCONNECT_P95_LIMIT_SECONDS


@pytest.mark.integration
class TestDisconnectEnforcementIdempotency:
    """Verify disconnect is idempotent and safe to retry."""

    @pytest.mark.asyncio
    async def test_double_revoke_is_idempotent(
        self, grant_service: GrantService, active_grant: AccessGrant
    ) -> None:
        """Revoking same grant twice succeeds without error."""
        result1 = await grant_service.revoke(active_grant.id)
        result2 = await grant_service.revoke(active_grant.id)
        assert result1.status == GrantStatus.REVOKED
        assert result2.status == GrantStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_sets_end_utc_to_current_time(
        self, grant_service: GrantService, active_grant: AccessGrant
    ) -> None:
        """Revoked grant's end_utc should be set to approximately now."""
        before = datetime.now(timezone.utc)
        result = await grant_service.revoke(active_grant.id)
        after = datetime.now(timezone.utc)

        # SQLite may strip timezone info; compare as naive UTC
        end = result.end_utc.replace(tzinfo=None) if result.end_utc.tzinfo else result.end_utc
        before_naive = before.replace(tzinfo=None)
        after_naive = after.replace(tzinfo=None)

        assert end >= before_naive - timedelta(seconds=1)
        assert end <= after_naive + timedelta(seconds=1)
