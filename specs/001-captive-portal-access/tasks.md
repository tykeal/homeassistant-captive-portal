SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Captive Portal Guest Access

**Input**: spec.md, phase1.md, plan.md (phased TDD)
**Prerequisites**: plan.md, spec.md, phase1.md

## Format: `[ID] [P] [Story] Description`
- **[P]** parallel-safe (different files/no deps)
- **[Story]** US1..US4 or NF (non-functional)

## Phase 0: Research & Environment Setup
- [x] T0001 [P] NF Initialize uv project, pyproject, base dependency pins (2025-10-24T21:39:11.207Z)
- [x] T0002 [P] NF Add pre-commit (ruff, reuse, pytest, coverage, trailing-ws) (2025-10-24T21:39:11.207Z)
- [x] T0003 [P] NF Add addon skeleton (Dockerfile, config.json, run script) from addons-example (2025-10-24T21:39:11.207Z)
- [x] T0004 NF research.md: document TP-Omada external portal endpoints (authorize, revoke, session) with sample payloads (2025-10-24T21:42:42.556Z)
- [x] T0005 NF research.md: document HA REST endpoints for Rental Control entities discovery (2025-10-24T21:42:42.556Z)
- [x] T0006 [P] NF Add basic FastAPI app factory + health endpoint (no business logic) (2025-10-24T21:39:11.207Z)
- [x] T0007 [P] NF Add logging & structured log formatter (JSON capable) (2025-10-24T21:39:11.207Z)
- [x] T0008 NF Phase 0 review: re-evaluate spec analysis & list decisions required for Phase 1 (2025-10-24T21:42:42.556Z)
- [x] T0009 NF constitution_gate_checklist.md created (initial gates) (2025-10-25T13:46:20.138Z)

## Phase 1: Data Model & Contracts (Write tests first)
### Tests First
- [x] T0100 [P] NF tests/unit/models/test_voucher_model.py (validation, duration calc) (2025-10-25T20:18:06.977Z)
- [x] T0101 [P] NF tests/unit/models/test_access_grant_model.py (2025-10-25T20:18:06.977Z)
- [x] T0102 [P] NF tests/unit/models/test_admin_account_model.py (password hash placeholder) (2025-10-25T20:18:06.977Z)
- [x] T0103 [P] NF tests/unit/models/test_entity_mapping_model.py (2025-10-25T20:18:06.977Z)
- [x] T0104 [P] NF tests/unit/models/test_audit_log_model.py (2025-10-25T20:18:06.977Z)
- [x] T0105 [P] US1 tests/contract/tp_omada/test_authorize_flow.py (fixture stubs fail initially) (2025-10-25T20:18:06.977Z)
- [x] T0106 [P] US1 tests/contract/tp_omada/test_revoke_flow.py (2025-10-25T20:18:06.977Z)
- [x] T0107 [P] US3 tests/contract/ha/test_entity_discovery.py (2025-10-25T20:18:06.977Z)
- [x] T0108 NF tests/unit/config/test_settings_load.py (2025-10-25T20:18:06.977Z)
- [x] T0109 NF tests/performance/test_baselines_placeholder.py (skipped; asserts p95 thresholds) (2025-10-25T20:18:06.977Z)

### Implementation
- [x] T0110 NF persistence/__init__.py repository abstractions (VoucherRepo, GrantRepo, AdminRepo) (2025-10-26T00:56:21.774Z)
- [x] T0111 NF persistence/sqlite_meta.py create tables via SQLModel (2025-10-26T00:56:21.774Z)
- [x] T0111a NF performance_baselines.md: capture baseline sources & methodology (links to plan) (2025-10-25T13:08:00.000Z)
- [x] T0112 [P] NF core/models/voucher.py (2025-10-25T20:25:09.143Z)
- [x] T0113 [P] NF core/models/access_grant.py (2025-10-25T20:27:38.792Z)
- [x] T0114 [P] NF core/models/admin_account.py (2025-10-25T20:30:42.556Z)
- [x] T0115 [P] NF core/models/entity_mapping.py (2025-10-25T20:30:42.556Z)
- [x] T0116 [P] NF core/models/audit_log.py (2025-10-25T20:30:42.556Z)
- [x] T0117 NF api/contracts/openapi_draft.yaml (initial endpoints) (2025-10-26T13:48:15.332Z)
- [x] T0118 NF contracts/controller/omada_authorize.json (request/response schema) (2025-10-26T13:48:15.332Z)
- [x] T0119 NF contracts/controller/omada_revoke.json (2025-10-26T13:48:15.332Z)
- [x] T0120 NF Phase 1 review: re-evaluate spec analysis & list decisions required for Phase 2 (2025-10-26T13:51:43.885Z)

## Phase 2: Core Services (Voucher & Grant Logic + RBAC Foundations)
### Tests First
- [x] T0200 [P] US1 tests/unit/services/test_voucher_service_create.py (duplicate prevention red) (2025-10-26T14:26:32.117Z)
- [x] T0201 [P] US1 tests/unit/services/test_voucher_service_redeem.py (expired, valid) (2025-10-26T14:26:32.117Z)
- [x] T0202 [P] US1 tests/unit/services/test_grant_service_create.py (2025-10-26T14:26:32.117Z)
- [x] T0203 [P] US2 tests/unit/services/test_grant_service_extend.py (2025-10-26T14:26:32.117Z)
- [x] T0204 [P] US2 tests/unit/services/test_grant_service_revoke.py (2025-10-26T14:26:32.117Z)
- [x] T0205 US1 tests/integration/test_duplicate_redemption_race.py (concurrency) (2025-10-26T14:26:32.117Z)
- [x] T0206 NF tests/integration/test_rbac_permission_matrix_allow.py (each role allowed actions) (2025-10-25T13:44:22.000Z)
- [x] T0207 NF tests/integration/test_rbac_permission_matrix_deny.py (deny-by-default unauthorized actions => 403) (2025-10-25T13:44:22.000Z)

### Implementation
- [ ] T0210 US1 services/voucher_service.py (create, validate, redeem)
- [ ] T0211 US1 services/grant_service.py (create, revoke, extend)
- [ ] T0212 NF services/audit_service.py (log admin + voucher events)
- [ ] T0213 NF concurrency lock / uniqueness (DB constraint + async lock) added
- [ ] T0215 NF security/rbac/matrix.py (role→actions mapping & deny-by-default lookup)
- [ ] T0216 NF middleware/rbac_enforcer.py (FastAPI dependency to enforce matrix, emits audit on deny)
- [ ] T0217 NF docs/permissions_matrix.md (roles x endpoints/actions table and RBAC acceptance criteria for FR-017)
- [ ] T0214 NF Phase 2 review: re-evaluate spec analysis & list decisions required for Phase 3

## Phase 3: Controller Integration (TP-Omada)
### Tests First
- [ ] T0300 [P] US1 tests/contract/tp_omada/test_adapter_error_retry.py (backoff)
- [ ] T0301 [P] US1 tests/integration/test_authorize_end_to_end.py
- [ ] T0302 [P] US1 tests/integration/test_revoke_end_to_end.py

### Implementation
- [ ] T0310 US1 controllers/tp_omada/base_client.py (HTTP wrapper)
- [ ] T0311 US1 controllers/tp_omada/adapter.py (authorize, revoke, update)
- [ ] T0312 US1 services/omada_sync_queue.py (retry queue)
- [ ] T0313 NF metrics instrumentation (authorize latency histogram)
- [ ] T0314 NF Phase 3 review: re-evaluate spec analysis & list decisions required for Phase 4

## Phase 4: Admin Web Interface & Theming
### Tests First
- [ ] T0400 [P] US2 tests/integration/test_admin_auth_login_logout.py
- [ ] T0401 [P] US2 tests/integration/test_admin_session_csrf.py
- [ ] T0402 [P] US2 tests/integration/test_admin_extend_revoke_grant.py
- [ ] T0403 [P] US2 tests/integration/test_admin_list_filters.py
- [ ] T0404 [P] US3 tests/integration/test_entity_mapping_save_retrieve.py
- [ ] T0405 [P] US4 tests/integration/test_initial_admin_bootstrap.py
- [ ] T0406 [P] US4 tests/integration/test_add_additional_admin.py

### Implementation
- [ ] T0410 US4 security/password_hashing.py
- [ ] T0411 US4 security/session_middleware.py (secure HTTP-only cookie, rotation)
- [ ] T0412 US4 security/csrf.py (token issue/verify)
- [ ] T0413 US2 api/routes/admin_auth.py (login/logout, bootstrap)
- [ ] T0414 US2 api/routes/grants.py (list/extend/revoke)
- [ ] T0415 US1 api/routes/vouchers.py (redeem)
- [ ] T0416 US3 api/routes/entity_mapping.py
- [ ] T0417 NF api/routes/health.py
- [ ] T0418 NF web/templates/portal/index.html (theming placeholders)
- [ ] T0419 NF web/templates/admin/dashboard.html
- [ ] T0420 NF web/themes/default/theme.css
- [ ] T0421 NF Phase 4 review: re-evaluate spec analysis & list decisions required for Phase 5

## Phase 5: Home Assistant Entity Mapping Integration (Booking Code Validation)
### Tests First
- [ ] T0500 [P] US3 tests/unit/services/test_entity_discovery_failover.py
- [ ] T0501 [P] US3 tests/integration/test_entity_mapping_applied_in_voucher_validation.py
- [ ] T0502 NF tests/unit/services/test_booking_code_format_validation.py (slot_code, slot_name edge cases + voucher length/charset per FR-018)
- [ ] T0503 NF tests/integration/test_booking_code_lookup_happy_path.py (event 0 & 1)
- [ ] T0504 NF tests/integration/test_booking_code_not_found.py
- [ ] T0505 NF tests/integration/test_booking_code_outside_window.py
- [ ] T0506 NF tests/integration/test_booking_code_duplicate_grant.py
- [ ] T0507 NF tests/integration/test_booking_code_integration_unavailable.py

### Implementation
- [ ] T0510 US3 services/ha_entity_service.py (fetch + cache)
- [ ] T0511 US3 services/mapping_application.py (inject entity data to validation)
- [ ] T0512 NF add degraded-mode logging when HA unreachable
- [ ] T0514 NF services/booking_code_validator.py (format+window+lookup logic, metrics, audit emission)
- [ ] T0515 NF api/routes/booking_authorize.py (guest POST code → grant)
- [ ] T0516 NF docs/booking_code_validation.md (FR-018 details, flows, error matrix)
- [ ] T0513 NF Phase 5 review: re-evaluate spec analysis & list decisions required for Phase 6

## Phase 6: Performance & Hardening
### Tests First
- [ ] T0600 NF tests/performance/test_redeem_latency.py (benchmark scaffold)
- [ ] T0601 NF tests/performance/test_admin_list_scaling.py
- [ ] T0602 NF tests/integration/test_audit_log_completeness.py

### Implementation / Optimization
- [ ] T0610 NF optimize DB indices (voucher.code, access_grant.expiration)
- [ ] T0611 NF add caching layer for frequently read vouchers (optional)
- [ ] T0612 NF finalize performance thresholds documentation
- [ ] T0613 NF Phase 6 review: re-evaluate spec analysis & list decisions required for Phase 7

## Phase 7: Polish & Documentation
- [ ] T0700 NF quickstart.md (addon + standalone run)
- [ ] T0701 NF README updates (principles summary, architecture)
- [ ] T0702 NF docs/addon/config.md (explain config.json options)
- [ ] T0703 NF finalize OpenAPI description & examples
- [ ] T0704 NF verify SPDX headers across repository
- [ ] T0705 NF security review checklist (session hardening, CSRF, headers)
- [ ] T0706 NF release notes draft (MVP scope)
- [ ] T0707 NF audit logging review & gap fixes

## Dependencies & Execution Order
- Completion of Phase 0 required before Phase 1.
- Core services (Phase 2) depend on models/contracts (Phase 1 partial) & contracts.
- Controller adapter (Phase 3) depends on services scaffolds (Phase 2 partial) & contracts.
- Admin interface (Phase 4) depends on auth + services + controller integration.
- Entity mapping (Phase 5) depends on earlier phases for validation injection.
- Performance & hardening (Phase 6) after core functionality stable.
- Polish (Phase 7) last.

## Parallel Opportunities
- Tasks marked [P] can run concurrently within a phase.
- Different user stories can proceed after their dependencies satisfied.
- Model files (T0112..T0116) all parallel.
- Controller integration tests (T0300..T0302) parallel.

## Notes
- All tests written first per phase (red) then implementation (green) then refactor.
- Commit each task or cohesive small set (atomic).
- Performance tests initially skipped until baseline chosen.
- Avoid introducing auth framework complexity beyond session + CSRF for v1.

## Remediation Addenda (Post-Analysis)
- Added after specification analysis to close coverage & alignment gaps.

### Remediation Tasks
- [ ] T0709 NF tests/integration/test_portal_error_messages_theming.py (guest error clarity, theming, localization placeholders) (FR-012).
- [ ] T0711 NF tests/unit/logging/test_audit_log_fields.py (validate user, action, resource, result, correlation_id) + ensure audit_service emits all fields.
- [ ] T0712 NF tests/integration/test_session_cookie_security_headers.py (Secure, HttpOnly, SameSite=Lax, CSP, Referrer-Policy, Permissions-Policy) & middleware header additions.
- [ ] T0713 NF tests/integration/test_theme_precedence.py (admin override > default > fallback) including error pages & vouchers.
- [ ] T0714 NF tests/integration/test_health_readiness_liveness.py + implement readiness & liveness endpoints & document container probes.
- [ ] T0715 NF cache_decision.md: decide keep (add NFR: reduce controller round-trips 60% + tests) or remove T0611; record rationale.
- [ ] T0716 NF add NFR (disconnect enforcement p95 <30s after access expiry) + tests/integration/test_disconnect_enforcement.py.
- [ ] T0717 NF extend metrics (active_sessions, controller_latency, auth_failures) + tests/unit/metrics/test_metrics_export.py & instrumentation updates.
- [ ] T0718 NF tests/integration/test_addon_build_run.py: build HA addon image, start container, verify health & readiness endpoints, graceful shutdown.
- Recommendation (2025-10-23T13:57:51.702Z): Adopt minimal in-memory TTL cache (30–60s controller status, 5–10m HA rental metadata) with explicit bust on grant create/update/delete; implement via optional layer (T0611) if T0715 outcome = keep, else remove T0611.
