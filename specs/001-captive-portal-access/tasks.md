SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Captive Portal Guest Access

**Input**: spec.md, plan.md (phased TDD)
**Prerequisites**: plan.md, spec.md

## Format: `[ID] [P] [Story] Description`
- **[P]** parallel-safe (different files/no deps)
- **[Story]** US1..US4 or NF (non-functional)

## Phase 0: Research & Environment Setup
- [ ] T0001 [P] NF Initialize uv project, pyproject, base dependency pins
- [ ] T0002 [P] NF Add pre-commit (ruff, reuse, pytest, coverage, trailing-ws)
- [ ] T0003 [P] NF Add addon skeleton (Dockerfile, config.json, run script) from addons-example
- [ ] T0004 NF research.md: document TP-Omada external portal endpoints (authorize, revoke, session) with sample payloads
- [ ] T0005 NF research.md: document HA REST endpoints for Rental Control entities discovery
- [ ] T0006 [P] NF Add basic FastAPI app factory + health endpoint (no business logic)
- [ ] T0007 [P] NF Add logging & structured log formatter (JSON capable)

## Phase 1: Data Model & Contracts (Write tests first)
### Tests First
- [ ] T0100 [P] NF tests/unit/models/test_voucher_model.py (validation, duration calc)
- [ ] T0101 [P] NF tests/unit/models/test_access_grant_model.py
- [ ] T0102 [P] NF tests/unit/models/test_admin_account_model.py (password hash placeholder)
- [ ] T0103 [P] NF tests/unit/models/test_entity_mapping_model.py
- [ ] T0104 [P] NF tests/unit/models/test_audit_log_model.py
- [ ] T0105 [P] US1 tests/contract/tp_omada/test_authorize_flow.py (fixture stubs fail initially)
- [ ] T0106 [P] US1 tests/contract/tp_omada/test_revoke_flow.py
- [ ] T0107 [P] US3 tests/contract/ha/test_entity_discovery.py
- [ ] T0108 NF tests/unit/config/test_settings_load.py

### Implementation
- [ ] T0110 NF persistence/__init__.py repository abstractions (VoucherRepo, GrantRepo, AdminRepo)
- [ ] T0111 NF persistence/sqlite_meta.py create tables via SQLModel
- [ ] T0112 [P] NF core/models/voucher.py
- [ ] T0113 [P] NF core/models/access_grant.py
- [ ] T0114 [P] NF core/models/admin_account.py
- [ ] T0115 [P] NF core/models/entity_mapping.py
- [ ] T0116 [P] NF core/models/audit_log.py
- [ ] T0117 NF api/contracts/openapi_draft.yaml (initial endpoints)
- [ ] T0118 NF contracts/controller/omada_authorize.json (request/response schema)
- [ ] T0119 NF contracts/controller/omada_revoke.json

## Phase 2: Core Services (Voucher & Grant Logic)
### Tests First
- [ ] T0200 [P] US1 tests/unit/services/test_voucher_service_create.py (duplicate prevention red)
- [ ] T0201 [P] US1 tests/unit/services/test_voucher_service_redeem.py (expired, valid)
- [ ] T0202 [P] US1 tests/unit/services/test_grant_service_create.py
- [ ] T0203 [P] US2 tests/unit/services/test_grant_service_extend.py
- [ ] T0204 [P] US2 tests/unit/services/test_grant_service_revoke.py
- [ ] T0205 US1 tests/integration/test_duplicate_redemption_race.py (concurrency)

### Implementation
- [ ] T0210 US1 services/voucher_service.py (create, validate, redeem)
- [ ] T0211 US1 services/grant_service.py (create, revoke, extend)
- [ ] T0212 NF services/audit_service.py (log admin + voucher events)
- [ ] T0213 NF concurrency lock / uniqueness (DB constraint + async lock) added

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

## Phase 5: Home Assistant Entity Mapping Integration
### Tests First
- [ ] T0500 [P] US3 tests/unit/services/test_entity_discovery_failover.py
- [ ] T0501 [P] US3 tests/integration/test_entity_mapping_applied_in_voucher_validation.py

### Implementation
- [ ] T0510 US3 services/ha_entity_service.py (fetch + cache)
- [ ] T0511 US3 services/mapping_application.py (inject entity data to validation)
- [ ] T0512 NF add degraded-mode logging when HA unreachable

## Phase 6: Performance & Hardening
### Tests First
- [ ] T0600 NF tests/performance/test_redeem_latency.py (benchmark scaffold)
- [ ] T0601 NF tests/performance/test_admin_list_scaling.py
- [ ] T0602 NF tests/integration/test_audit_log_completeness.py

### Implementation / Optimization
- [ ] T0610 NF optimize DB indices (voucher.code, access_grant.expiration)
- [ ] T0611 NF add caching layer for frequently read vouchers (optional)
- [ ] T0612 NF finalize performance thresholds documentation

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
- Core services (Phase 2) depend on models/contracts (Phase 1).
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
