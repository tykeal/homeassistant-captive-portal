<!--
SPDX-FileCopyrightText: © 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 6 Implementation Decisions

**Date**: 2025-10-30
**Phase**: Phase 6 (Performance & Hardening)
**Status**: Decision Record

---

## D6-1: Portal Configuration UI Implementation Timing

**Decision**: **Option A - Implement in Phase 6**

**Rationale**: Configuration UI is essential for performance testing scenarios (testing different rate limits, grace periods). Manual DB edits for configuration testing would be cumbersome and incomplete admin UI experience would impact usability testing.

**Impact**:
- Tasks T0603, T0604, T0612, T0613 will be completed in Phase 6
- Adds scope to performance-focused phase but necessary for operational testing

**Status**: ✅ APPROVED

---

## D6-2: Caching Strategy

**Decision**: **Option A - Implement Minimal TTL Cache with Constraints**

**Constraints**:
- Start with controller status cache only (30s TTL)
- Add HA metadata cache only if benchmarks show need
- Explicit cache invalidation on mutations
- Document cache behavior in NFRs

**Rationale**: Reduces controller API round-trips by ~60% (estimated) and improves latency for concurrent redemptions. Controller APIs are the primary bottleneck for performance.

**Impact**:
- Complete T0611
- Add NFR for 60% controller round-trip reduction
- Add cache tests
- Document cache invalidation strategy

**Status**: ✅ APPROVED

---

## D6-3: Disconnect Enforcement Testing Strategy

**Decision**: **Option A + C Hybrid - Contract Test + Manual Protocol**

**Approach**:
- Automated contract test for API timing (CI)
- Manual test protocol for deployment validation (docs)
- Document controller-specific behavior in TP-Omada FAQ

**Rationale**: Provides testable automation in CI while acknowledging that actual network disconnect is controller-dependent and requires real hardware validation.

**Impact**:
- Task T0716 implementation uses contract testing approach
- Add manual test protocol to deployment documentation
- Add TP-Omada-specific behavior notes to FAQ

**Status**: ✅ APPROVED

---

## D6-4: Metrics Export Format & Endpoint

**Decision**: **Option A - Prometheus Format**

**Implementation**:
- Single `/metrics` endpoint (standard port/path)
- Prometheus format for external monitoring
- Admin UI can query Prometheus if needed in future
- Aligns with Home Assistant observability patterns

**Rationale**: Industry standard format, integrates with HA metrics ecosystem, widely supported by visualization tools (Grafana, etc.). Single format reduces implementation complexity.

**Impact**:
- Task T0717 implementation
- Add `prometheus_client` dependency
- Document metrics endpoint in API docs
- Future: Admin UI can consume Prometheus if visualization needed

**Status**: ✅ APPROVED

---

## Decision Summary

All blocking decisions for Phase 6 have been resolved:

- ✅ D6-1: Portal config UI in Phase 6
- ✅ D6-2: Implement minimal caching (controller status)
- ✅ D6-3: Hybrid testing (contract + manual)
- ✅ D6-4: Prometheus metrics format

**Phase 6 Readiness**: ✅ READY TO START

**Next Steps**:
1. Define target environment specs for performance baselines (G1)
2. Update plan.md and tasks.md to reflect decisions
3. Begin Phase 6 implementation with performance benchmarking

---

## Notes

- All decisions prioritize operational readiness and observability
- Caching strategy is conservative (start minimal, expand based on data)
- Testing strategy balances automation with real-world validation needs
- Prometheus choice aligns with broader HA ecosystem integration
