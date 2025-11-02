SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Performance Baselines

Source of record: plan.md (Performance Baselines section). This file documents methodology & initial placeholder test linkage.

## Targets (p95 unless noted)
- Voucher redemption: ≤800ms (L1: 50 concurrent) / ≤900ms (L2: 200 concurrent)
- Auth login API: ≤300ms
- Controller propagation (authorize→active): ≤25s
- Admin grants list (500 grants): ≤1500ms
- Memory RSS: ≤150MB
- CPU 1‑min peak: ≤60% @ 200 concurrent (container level)
- Regression gate: >10% degradation vs committed baseline blocks merge.

## Methodology
| Metric | Tool / Location | Notes |
|--------|-----------------|-------|
| Voucher redemption latency | tests/performance/test_redeem_latency.py | k6/Gatling placeholder; Python runner baseline capture phase 1 skipped initially |
| Auth login API latency | tests/performance/test_redeem_latency.py (login step) | Measures POST /admin/login excluding first TLS handshake warmup |
| Controller propagation | tests/integration/test_authorize_end_to_end.py | Timestamp authorize request until controller active confirmation |
| Admin grants list page | tests/performance/test_admin_list_scaling.py | Pre-seed 500 grants fixtures; measure first render excluding asset cache |
| Memory RSS | /proc/self/statm sampled via psutil in perf tests | Peak over test window; ignore first 5s warmup |
| CPU utilization | Docker stats API sampled every 2s | Compute 1‑min rolling max during load |

## Test Scaffold
- T0109 adds skipped baseline assertion test referencing these numbers.
- T0600/T0601 implement concrete load loops with actual assertions against targets.

## Performance Test Implementation Status
All performance benchmarks are implemented with actual assertions:

### Voucher Redemption Tests (`test_redeem_latency.py`)
- **test_voucher_redemption_latency_l1_50_concurrent**: 50 concurrent requests × 3 repetitions, p95 ≤ 800ms
- **test_voucher_redemption_latency_l2_200_concurrent**: 200 concurrent requests × 2 repetitions, p95 ≤ 900ms
- **test_admin_login_latency_p95**: 50 sequential logins, p95 ≤ 300ms

### Admin List Scaling Tests (`test_admin_list_scaling.py`)
- **test_admin_grants_list_500_grants_p95**: List 500 grants × 20 samples, p95 ≤ 1500ms
- **test_admin_vouchers_list_100_vouchers_p95**: List 100 vouchers × 20 samples (informational baseline)

### Outstanding Metrics
The following metrics from the baseline targets require manual validation or integration testing:
- **Controller propagation (authorize→active)**: ≤25s - Tested in `test_authorize_end_to_end.py` but requires real controller
- **Memory RSS**: ≤150MB - Requires container runtime monitoring
- **CPU 1-min peak**: ≤60% @ 200 concurrent - Requires container runtime monitoring

## Running Performance Tests
```bash
# Run all performance tests
uv run pytest -v -m performance

# Run specific test with output
uv run pytest -v -s tests/performance/test_redeem_latency.py::test_voucher_redemption_latency_l1_50_concurrent
```

## Maintenance
- Update only via dedicated task referencing change rationale (e.g., hardware change, architecture optimization).
- Any upward adjustment requires explicit justification and sign-off in PR description.
- Performance tests marked with `@pytest.mark.performance` for selective execution.
