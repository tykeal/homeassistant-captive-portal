# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Performance tests for voucher redemption latency benchmarks."""

import asyncio
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from captive_portal.models.voucher import Voucher
from captive_portal.persistence.database import get_session

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.performance
async def test_voucher_redemption_latency_l1_50_concurrent(
    async_client: "AsyncClient",
) -> None:
    """
    Benchmark voucher redemption latency at L1 load (50 concurrent).

    Performance target: p95 <= 800ms
    """
    # GIVEN: Test client and vouchers
    concurrent_requests = 50
    repetitions = 3  # Run each voucher 3 times for better percentile data

    # Create test vouchers
    vouchers: list[str] = []
    session = next(get_session())
    try:
        for i in range(concurrent_requests):
            voucher = Voucher(
                code=f"BENCH{i:04d}L1",
                device_limit=10,
                created_utc=datetime.now(UTC),
                expires_utc=datetime.now(UTC) + timedelta(hours=24),
            )
            session.add(voucher)
            vouchers.append(voucher.code)
        session.commit()
    finally:
        session.close()

    # WHEN: Measuring redemption latency across concurrent requests
    async def redeem_voucher(code: str, mac: str) -> float:
        """Redeem a voucher and return latency in milliseconds."""
        start = time.perf_counter()
        client = async_client
        response = await client.post(
            "/guest/redeem",
            json={"code": code, "mac_address": mac},
        )
        # Check that request succeeded for valid benchmarking
        assert response.status_code in (
            200,
            201,
        ), f"Redemption failed: {response.text}"
        elapsed = time.perf_counter() - start
        return elapsed * 1000  # Convert to milliseconds

    # Run benchmark
    latencies: list[float] = []
    for run in range(repetitions):
        tasks = [
            redeem_voucher(
                vouchers[i],
                f"00:11:22:33:44:{i:02x}:run{run}",
            )
            for i in range(concurrent_requests)
        ]
        run_latencies = await asyncio.gather(*tasks)
        latencies.extend(run_latencies)

    # THEN: Calculate p95 latency
    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    p95_index = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[p95_index]
    p99_index = int(len(latencies_sorted) * 0.99)
    p99 = latencies_sorted[p99_index]

    print(f"\nL1 Benchmark Results ({concurrent_requests} concurrent, {repetitions} runs):")  # noqa: T201
    print(f"  Samples: {len(latencies)}")  # noqa: T201
    print(f"  p50: {p50:.2f}ms")  # noqa: T201
    print(f"  p95: {p95:.2f}ms (target: <=800ms)")  # noqa: T201
    print(f"  p99: {p99:.2f}ms")  # noqa: T201

    # Assert against baseline
    assert p95 <= 800.0, f"L1 p95 latency {p95:.2f}ms exceeds 800ms target"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_voucher_redemption_latency_l2_200_concurrent(
    async_client: "AsyncClient",
) -> None:
    """
    Benchmark voucher redemption latency at L2 load (200 concurrent).

    Performance target: p95 <= 900ms
    """
    # GIVEN: Test client and vouchers
    concurrent_requests = 200
    repetitions = 2  # Fewer reps for L2 due to volume

    # Create test vouchers
    vouchers: list[str] = []
    session = next(get_session())
    try:
        for i in range(concurrent_requests):
            voucher = Voucher(
                code=f"BENCH{i:04d}L2",
                device_limit=10,
                created_utc=datetime.now(UTC),
                expires_utc=datetime.now(UTC) + timedelta(hours=24),
            )
            session.add(voucher)
            vouchers.append(voucher.code)
        session.commit()
    finally:
        session.close()

    # WHEN: Measuring redemption latency across concurrent requests
    async def redeem_voucher(code: str, mac: str) -> float:
        """Redeem a voucher and return latency in milliseconds."""
        start = time.perf_counter()
        client = async_client
        response = await client.post(
            "/guest/redeem",
            json={"code": code, "mac_address": mac},
        )
        assert response.status_code in (
            200,
            201,
        ), f"Redemption failed: {response.text}"
        elapsed = time.perf_counter() - start
        return elapsed * 1000

    # Run benchmark
    latencies: list[float] = []
    for run in range(repetitions):
        tasks = [
            redeem_voucher(
                vouchers[i],
                f"00:11:22:33:44:{i:02x}:run{run}",
            )
            for i in range(concurrent_requests)
        ]
        run_latencies = await asyncio.gather(*tasks)
        latencies.extend(run_latencies)

    # THEN: Calculate p95 latency
    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    p95_index = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[p95_index]
    p99_index = int(len(latencies_sorted) * 0.99)
    p99 = latencies_sorted[p99_index]

    print(f"\nL2 Benchmark Results ({concurrent_requests} concurrent, {repetitions} runs):")  # noqa: T201
    print(f"  Samples: {len(latencies)}")  # noqa: T201
    print(f"  p50: {p50:.2f}ms")  # noqa: T201
    print(f"  p95: {p95:.2f}ms (target: <=900ms)")  # noqa: T201
    print(f"  p99: {p99:.2f}ms")  # noqa: T201

    # Assert against baseline
    assert p95 <= 900.0, f"L2 p95 latency {p95:.2f}ms exceeds 900ms target"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_admin_login_latency_p95(async_client: "AsyncClient") -> None:
    """
    Benchmark admin login API latency.

    Performance target: p95 <= 300ms
    """
    # GIVEN: Test client and admin credentials
    from captive_portal.models.admin_user import AdminUser
    from captive_portal.security.password_hashing import hash_password

    # Create test admin
    session = next(get_session())
    try:
        admin = AdminUser(
            username="benchmark_admin",
            password_hash=hash_password("benchmark_password"),
            email="benchmark_admin@test.local",
            role="admin",
            created_utc=datetime.now(UTC),
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    # WHEN: Measuring login latency
    async def perform_login() -> float:
        """Perform login and return latency in milliseconds."""
        start = time.perf_counter()
        client = async_client
        response = await client.post(
            "/admin/login",
            data={"username": "benchmark_admin", "password": "benchmark_password"},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        elapsed = time.perf_counter() - start
        return elapsed * 1000

    # Run benchmark (50 samples for login)
    latencies = [await perform_login() for _ in range(50)]

    # THEN: Calculate p95 latency
    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    p95_index = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[p95_index]
    p99_index = int(len(latencies_sorted) * 0.99)
    p99 = latencies_sorted[p99_index]

    print("\nAdmin Login Benchmark Results:")  # noqa: T201
    print(f"  Samples: {len(latencies)}")  # noqa: T201
    print(f"  p50: {p50:.2f}ms")  # noqa: T201
    print(f"  p95: {p95:.2f}ms (target: <=300ms)")  # noqa: T201
    print(f"  p99: {p99:.2f}ms")  # noqa: T201

    # Assert against baseline
    assert p95 <= 300.0, f"Admin login p95 latency {p95:.2f}ms exceeds 300ms target"
