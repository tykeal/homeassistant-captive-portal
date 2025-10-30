# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Performance tests for admin list operations scaling."""

import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from captive_portal.models.access_grant import AccessGrant
from captive_portal.models.admin_user import AdminUser
from captive_portal.persistence.database import get_session
from captive_portal.security.password_hashing import hash_password

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.performance
async def test_admin_grants_list_500_grants_p95(async_client: "AsyncClient") -> None:
    """
    Benchmark admin grants list with 500 grants.

    Performance target: p95 <= 1500ms
    """
    # GIVEN: Admin user and 500 grants
    session = next(get_session())
    try:
        # Create admin user
        admin = AdminUser(
            username="list_benchmark_admin",
            password_hash=hash_password("benchmark_password"),
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.flush()

        # Create 500 access grants
        base_time = datetime.now(UTC)
        for i in range(500):
            grant = AccessGrant(
                mac_address=f"AA:BB:CC:DD:EE:{i:02x}",
                start_utc=base_time - timedelta(hours=i % 24),
                end_utc=base_time + timedelta(hours=24 - (i % 12)),
                created_by_admin_id=admin.id,
                source_type="voucher" if i % 2 == 0 else "booking",
                source_identifier=f"BENCH{i:04d}",
            )
            session.add(grant)
        session.commit()
    finally:
        session.close()

    # WHEN: Measuring grants list latency
    async def fetch_grants_list() -> float:
        """Fetch grants list and return latency in milliseconds."""
        # Login first
        async with async_client as client:
            login_response = await client.post(
                "/admin/login",
                data={
                    "username": "list_benchmark_admin",
                    "password": "benchmark_password",
                },
            )
            assert login_response.status_code == 200

            # Measure list operation
            start = time.perf_counter()
            response = await client.get("/admin/grants")
            assert response.status_code == 200
            elapsed = time.perf_counter() - start

        return elapsed * 1000  # Convert to milliseconds

    # Run benchmark (20 samples)
    latencies = [await fetch_grants_list() for _ in range(20)]

    # THEN: Calculate percentiles
    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    p95_index = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[p95_index]
    p99_index = int(len(latencies_sorted) * 0.99)
    p99 = latencies_sorted[p99_index]

    print("\nAdmin Grants List Benchmark (500 grants):")  # noqa: T201
    print(f"  Samples: {len(latencies)}")  # noqa: T201
    print(f"  p50: {p50:.2f}ms")  # noqa: T201
    print(f"  p95: {p95:.2f}ms (target: <=1500ms)")  # noqa: T201
    print(f"  p99: {p99:.2f}ms")  # noqa: T201

    # Assert against baseline
    assert p95 <= 1500.0, f"Admin grants list p95 latency {p95:.2f}ms exceeds 1500ms target"


@pytest.mark.performance
async def test_admin_vouchers_list_100_vouchers_p95(
    async_client: "AsyncClient",
) -> None:
    """
    Benchmark admin vouchers list with 100 vouchers.

    No explicit target, but should be comparable to grants list.
    """
    # GIVEN: Admin user and 100 vouchers
    from captive_portal.models.voucher import Voucher

    session = next(get_session())
    try:
        # Create admin user
        admin = AdminUser(
            username="voucher_list_admin",
            password_hash=hash_password("benchmark_password"),
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.flush()

        # Create 100 vouchers
        base_time = datetime.now(UTC)
        for i in range(100):
            voucher = Voucher(
                code=f"VLIST{i:05d}",
                device_limit=5 + (i % 10),
                created_utc=base_time - timedelta(hours=i % 48),
                expires_utc=base_time + timedelta(days=7 - (i % 5)),
                created_by_admin_id=admin.id,
            )
            session.add(voucher)
        session.commit()
    finally:
        session.close()

    # WHEN: Measuring vouchers list latency
    async def fetch_vouchers_list() -> float:
        """Fetch vouchers list and return latency in milliseconds."""
        async with async_client as client:
            login_response = await client.post(
                "/admin/login",
                data={
                    "username": "voucher_list_admin",
                    "password": "benchmark_password",
                },
            )
            assert login_response.status_code == 200

            start = time.perf_counter()
            response = await client.get("/admin/vouchers")
            assert response.status_code == 200
            elapsed = time.perf_counter() - start

        return elapsed * 1000

    # Run benchmark (20 samples)
    latencies = [await fetch_vouchers_list() for _ in range(20)]

    # THEN: Calculate percentiles
    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    p95_index = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[p95_index]

    print("\nAdmin Vouchers List Benchmark (100 vouchers):")  # noqa: T201
    print(f"  Samples: {len(latencies)}")  # noqa: T201
    print(f"  p50: {p50:.2f}ms")  # noqa: T201
    print(f"  p95: {p95:.2f}ms")  # noqa: T201

    # No strict assertion, but log results for comparison
