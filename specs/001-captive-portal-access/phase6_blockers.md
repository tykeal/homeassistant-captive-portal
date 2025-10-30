<!--
SPDX-FileCopyrightText: © 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 6 Blockers & Open Issues Analysis

**Date**: 2025-10-30
**Branch**: 001-captive-portal-access
**Phase**: Phase 5 Complete → Phase 6 Prep
**Status**: Draft (Do Not Commit)

## Executive Summary

Phase 5 (Guest Portal & Authentication) is functionally complete with all core features implemented and tested. The following analysis identifies open issues, decisions, and gaps that need resolution before Phase 6 (Performance & Hardening) can proceed.

**Overall Health**: ✅ Good - Core functionality complete, no critical blockers
**Tests**: 381 tests collected, Phase 5 tests passing
**Code Review**: Final code review completed, all issues resolved

---

## Category 1: BLOCKING DECISIONS FOR PHASE 6

### D23: Portal Configuration UI Implementation Timing
**Status**: ⚠️ NEEDS DECISION
**Context**: Phase 5 implemented PortalConfig model (rate limits, grace periods, redirect behavior) but deferred UI to Phase 6 per task T0613.

**Question**: Should portal configuration UI be completed in Phase 6 or deferred to Phase 7 (Polish)?

**Options**:
- **A) Phase 6**: Implement UI during Performance & Hardening phase since it affects operational testing
  - Pro: Enables testing of different rate limit configurations
  - Pro: Required for admin to adjust performance-related settings
  - Con: Adds scope to performance-focused phase

- **B) Phase 7**: Defer to Polish & Documentation phase
  - Pro: Keeps Phase 6 focused on optimization
  - Con: Manual DB edits needed for configuration testing
  - Con: Incomplete admin UI experience

**Recommendation**: Option A - Implement in Phase 6. Configuration UI is essential for performance testing scenarios (testing different rate limits, grace periods).

**Impact**: Tasks T0603, T0604, T0612, T0613 need completion

---

### D24: Caching Strategy Decision
**Status**: ⚠️ NEEDS DECISION (Referenced in T0715)
**Context**: Task T0611 proposes optional caching layer for frequently read vouchers. Task T0715 requires explicit decision with documented rationale.

**Question**: Should we implement in-memory caching for voucher/grant lookups?

**Options**:
- **A) Implement Minimal TTL Cache**
  - Scope: 30-60s TTL for controller status, 5-10min for HA rental metadata
  - Pro: Reduces controller API round-trips by ~60% (estimated)
  - Pro: Improves latency for concurrent redemptions
  - Con: Adds complexity (cache invalidation, consistency)
  - Con: Requires cache bust on grant create/update/delete

- **B) Defer Caching (No Cache in v1)**
  - Pro: Simpler architecture, easier to reason about
  - Pro: Avoid premature optimization
  - Con: Higher controller API load during peak usage
  - Con: May not meet p95 latency targets under load

**Recommendation**: Option A with constraints:
- Start with controller status cache only (30s TTL)
- Add HA metadata cache only if benchmarks show need
- Explicit cache invalidation on mutations
- Document cache behavior in NFRs

**Impact**:
- If YES: Complete T0611, add NFR for 60% controller round-trip reduction, add cache tests
- If NO: Remove T0611, document rationale in cache_decision.md

---

### D25: Disconnect Enforcement Testing Strategy
**Status**: ⚠️ NEEDS DECISION (Referenced in T0716)
**Context**: NFR requires "disconnect enforcement p95 <30s after access expiry". TP-Omada controller handles actual disconnection.

**Question**: How do we test disconnect enforcement when it's controller-dependent?

**Options**:
- **A) Contract Test with Mock Controller**
  - Test that revocation API is called within timeframe
  - Mock controller confirms receipt
  - Pro: Testable in CI
  - Con: Doesn't validate actual network disconnect

- **B) Integration Test with Real Controller**
  - Requires TP-Omada hardware/container for testing
  - Pro: End-to-end validation
  - Con: Not feasible in standard CI
  - Con: Requires test infrastructure

- **C) Manual Test Protocol + Documentation**
  - Document test procedure for deployment validation
  - Include in quickstart/admin docs
  - Pro: Realistic testing
  - Con: Not automated

**Recommendation**: Option A + C hybrid:
- Automated contract test for API timing (CI)
- Manual test protocol for deployment validation (docs)
- Document controller-specific behavior in TP-Omada FAQ

**Impact**: Task T0716 implementation approach

---

### D26: Metrics Export Format & Endpoint
**Status**: ⚠️ NEEDS DECISION (Referenced in T0717)
**Context**: Task T0717 requires extending metrics (active_sessions, controller_latency, auth_failures).

**Question**: What format and exposure mechanism for metrics?

**Options**:
- **A) Prometheus Format (/metrics endpoint)**
  - Standard observability format
  - Pro: Industry standard, integrates with HA metrics
  - Pro: Many visualization tools (Grafana, etc.)
  - Con: Adds prometheus_client dependency

- **B) JSON Format (/api/admin/metrics endpoint)**
  - Simple JSON response
  - Pro: No additional dependencies
  - Pro: Easy to consume in admin UI
  - Con: Less standard, requires custom integration

- **C) Both Formats**
  - Prometheus for external monitoring
  - JSON for admin UI display
  - Pro: Maximum flexibility
  - Con: Duplicate implementation

**Recommendation**: Option A (Prometheus) for v1:
- Single `/metrics` endpoint (standard port/path)
- Admin UI can query Prometheus if needed in future
- Aligns with Home Assistant observability patterns

**Impact**: Task T0717 implementation, new dependency

---

## Category 2: TECHNICAL DEBT & GAPS

### G1: Performance Baseline Finalization
**Status**: ⚠️ INCOMPLETE
**Current State**: Baseline thresholds documented in plan.md but not enforced in tests
**Affected Tasks**: T0600, T0601, T0614
**Tests**: `tests/performance/test_baselines_placeholder.py` currently skipped

**Required Actions**:
1. Implement actual performance benchmark tests (T0600, T0601)
2. Run benchmarks on target hardware (or reasonable facsimile)
3. Validate against documented thresholds:
   - Voucher redemption: ≤800ms (L1: 50 concurrent) / ≤900ms (L2: 200 concurrent)
   - Auth login API: ≤300ms
   - Controller propagation: ≤25s
   - Admin grants list (500 grants): ≤1500ms
4. Update tests to enforce thresholds (remove skips)
5. Document methodology in performance_baselines.md

**Blocker**: Need target deployment environment specs for baseline calibration

---

### G2: Audit Log Completeness Validation
**Status**: ⚠️ INCOMPLETE
**Current State**: Audit logging implemented throughout Phase 5 but no comprehensive validation
**Affected Tasks**: T0602, T0711
**Required Fields**: user, action, resource, result, correlation_id (per T0711)

**Required Actions**:
1. Create `tests/integration/test_audit_log_completeness.py` (T0602)
2. Validate all admin actions generate audit entries
3. Validate all guest authorization attempts logged
4. Validate all controller operations logged
5. Ensure correlation_id propagation for request tracing
6. Test audit log retention and cleanup

**Current Coverage**: Partial - audit_service exists, needs comprehensive verification

---

### G3: Session Security Headers Completeness
**Status**: ⚠️ INCOMPLETE
**Current State**: Security headers partially implemented
**Affected Tasks**: T0712
**Required Headers**: Secure, HttpOnly, SameSite=Lax, CSP, Referrer-Policy, Permissions-Policy

**Required Actions**:
1. Create comprehensive header tests (T0712)
2. Validate all security headers present and correct
3. Test CSP policy prevents XSS
4. Test Referrer-Policy prevents leakage
5. Document header choices in security review

**Current Coverage**: Basic headers present, needs validation

---

### G4: Theme Precedence Testing
**Status**: ⚠️ INCOMPLETE
**Current State**: Theming implemented but precedence not fully tested
**Affected Tasks**: T0713
**Expected Behavior**: Admin override > default > fallback

**Required Actions**:
1. Create theme precedence tests (T0713)
2. Test admin-configured theme overrides default
3. Test fallback when admin theme missing
4. Test error page theming
5. Test voucher redemption page theming

**Current Coverage**: Basic theming works, precedence untested

---

### G5: Health/Readiness/Liveness Endpoints
**Status**: ⚠️ INCOMPLETE
**Current State**: Basic /health endpoint exists, no readiness/liveness separation
**Affected Tasks**: T0714, T0718
**Container Requirement**: Proper probe configuration for Kubernetes/HA addon

**Required Actions**:
1. Implement `/health/live` (process alive)
2. Implement `/health/ready` (dependencies available: DB, controller)
3. Create endpoint tests (T0714)
4. Create addon build/run test (T0718)
5. Document probe configuration in addon config.md

**Current Coverage**: Basic health check only

---

### G6: Error Message Theming & Localization
**Status**: ⚠️ INCOMPLETE
**Current State**: Error messages functional but not themed/localized
**Affected Tasks**: T0709
**FR Reference**: FR-012 (clear error messages without internal details)

**Required Actions**:
1. Create error message theming tests (T0709)
2. Validate guest error messages are clear and non-technical
3. Test error page applies theme (CSS variables)
4. Add localization placeholders (future i18n support)
5. Test all error scenarios from FR-018 (invalid_format, not_found, outside_window, duplicate)

**Current Coverage**: Functional errors, styling incomplete

---

## Category 3: REMEDIATION TASKS (Still Pending)

The following remediation tasks from the original task list remain incomplete:

- **T0709**: Error message theming tests (addressed in G6 above)
- **T0711**: Audit log fields validation (addressed in G2 above)
- **T0712**: Session cookie security headers (addressed in G3 above)
- **T0713**: Theme precedence tests (addressed in G4 above)
- **T0714**: Health/readiness/liveness (addressed in G5 above)
- **T0715**: Cache decision documentation (addressed in D24 above)
- **T0716**: Disconnect enforcement tests (addressed in D25 above)
- **T0717**: Metrics extension (addressed in D26 above)
- **T0718**: Addon build/run test (addressed in G5 above)

**Recommendation**: Address these in Phase 6 as part of hardening work.

---

## Category 4: DOCUMENTATION GAPS

### G7: API Documentation Completeness
**Status**: ⚠️ INCOMPLETE
**Required**: OpenAPI specification with examples (T0703)
**Current State**: contracts/openapi_draft.yaml exists but incomplete

**Required Actions**:
1. Complete OpenAPI spec for all endpoints
2. Add request/response examples
3. Document error responses with codes
4. Add authentication requirements
5. Generate API documentation

---

### G8: Addon Configuration Documentation
**Status**: ⚠️ INCOMPLETE
**Required**: docs/addon/config.md explaining config.json options (T0702)
**Current State**: Basic addon skeleton exists, config not documented

**Required Actions**:
1. Document all config.json options
2. Document environment variables
3. Document volume mounts
4. Document network requirements
5. Add troubleshooting section

---

### G9: Quickstart Documentation
**Status**: ⚠️ INCOMPLETE
**Required**: quickstart.md for addon + standalone deployment (T0700)
**Current State**: No quickstart guide

**Required Actions**:
1. Write quickstart for HA addon installation
2. Write quickstart for standalone container deployment
3. Include first-time setup (admin bootstrap)
4. Include common configuration scenarios
5. Include verification steps

---

## Category 5: NON-BLOCKING IMPROVEMENTS

### I1: Database Optimization
**Recommendation**: Add indices for common query paths
**Affected Task**: T0610
**Impact**: Low-Medium (performance improvement)

**Suggested Indices**:
- `voucher.code` (already unique, may need covering index)
- `access_grant.expiration_utc` (for cleanup queries)
- `access_grant.status` (for filtering active grants)
- `audit_log.created_utc` (for time-range queries)

---

### I2: REUSE/SPDX Compliance Verification
**Recommendation**: Automated verification in Phase 7
**Affected Task**: T0704
**Impact**: Low (compliance)

**Note**: pre-commit already runs reuse lint, needs final verification

---

### I3: Security Review Checklist
**Recommendation**: Comprehensive security audit before v1 release
**Affected Task**: T0705
**Impact**: Medium-High (security)

**Areas to Review**:
- Session management (idle timeout, absolute timeout, rotation)
- CSRF protection coverage
- XSS prevention (template escaping, CSP)
- SQL injection prevention (parameterized queries)
- Rate limiting effectiveness
- Redirect validation (open redirect prevention)
- Sensitive data handling (password hashing, no plaintext storage)

---

## PHASE 6 READINESS CHECKLIST

### Prerequisites Before Phase 6 Start:
- [ ] **D23**: Decide portal config UI timing (Phase 6 vs Phase 7)
- [ ] **D24**: Decide caching strategy (implement vs defer)
- [ ] **D25**: Decide disconnect enforcement testing approach
- [ ] **D26**: Decide metrics export format (Prometheus vs JSON)
- [ ] **G1**: Define target environment for performance baseline calibration

### Tasks Ready to Start (No Decisions Needed):
- [x] T0600: Performance benchmark tests (can start)
- [x] T0601: Admin list scaling tests (can start)
- [x] T0602: Audit log completeness (can start)
- [x] T0610: Database indices (can start)
- [ ] T0611: Caching (blocked by D24)
- [ ] T0612-T0613: Portal config UI (blocked by D23)
- [x] T0614: Performance docs (can start after T0600/T0601)

### Phase 5 Cleanup Needed:
- [ ] Mark T0533 (Phase 5 review) as complete
- [ ] Verify all Phase 5 tests are passing
- [ ] Verify pre-commit passes cleanly

---

## RECOMMENDATIONS FOR NEXT STEPS

### Immediate Actions (Before Phase 6):
1. **Walk through blocking decisions D23-D26** with user to get approvals
2. **Define target environment specs** for performance baselines (G1)
3. **Mark T0533 complete** (Phase 5 review done)
4. **Update tasks.md** to reflect current status

### Phase 6 Execution Order (After Decisions):
1. **Week 1**: Performance infrastructure
   - Implement benchmark tests (T0600, T0601)
   - Run baselines on target environment
   - Document methodology (T0614)

2. **Week 2**: Hardening - Core
   - Audit log completeness (T0602, T0711)
   - Security headers (T0712)
   - Health endpoints (T0714)

3. **Week 3**: Hardening - Features
   - Theme precedence (T0713)
   - Error message theming (T0709)
   - Disconnect enforcement (T0716)
   - Metrics extension (T0717)

4. **Week 4**: Optimization & Config UI
   - Database indices (T0610)
   - Caching (T0611) - if approved
   - Portal config UI (T0612, T0613) - if Phase 6
   - Addon build test (T0718)

### Phase 7 Planning:
- Documentation completion (T0700-T0703)
- Security review (T0705)
- SPDX verification (T0704)
- Release notes (T0706)

---

## RISK ASSESSMENT

### High Risk:
- ❌ None identified

### Medium Risk:
- ⚠️ **Performance baselines without target hardware**: May need recalibration in production
- ⚠️ **Caching complexity**: If implemented, adds potential consistency issues

### Low Risk:
- ℹ️ **Documentation gaps**: Can be completed in Phase 7
- ℹ️ **Theme precedence**: Low impact on core functionality

---

## SUMMARY

**Phase 5 Status**: ✅ Complete (functionality)
**Blocking Decisions**: 4 (D23-D26)
**Technical Gaps**: 6 (G1-G6)
**Remediation Tasks**: 9 (cross-referenced with gaps/decisions)
**Documentation Gaps**: 3 (G7-G9)

**Can Start Phase 6?**: ⚠️ PARTIAL - Can start performance benchmarking and some hardening tasks, but need decisions D23-D26 for full execution.

**Recommended Path**:
1. Resolve D23-D26 decisions (this session)
2. Define performance baseline environment
3. Start Phase 6 with benchmarking + hardening tasks
4. Complete portal config UI and caching based on decisions
5. Phase 7 for documentation and polish
