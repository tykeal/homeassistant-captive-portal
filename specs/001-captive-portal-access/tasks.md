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
- [x] T0210 US1 services/voucher_service.py (create, validate, redeem) (2025-10-26T14:32:17.418Z)
- [x] T0211 US1 services/grant_service.py (create, revoke, extend) (2025-10-26T14:35:45.092Z)
- [x] T0212 NF services/audit_service.py (log admin + voucher events) (2025-10-26T14:39:28.761Z)
- [x] T0213 NF concurrency lock / uniqueness (DB constraint + async lock) added (2025-10-26T14:40:00.000Z)
- [x] T0215 NF security/rbac/matrix.py (role→actions mapping & deny-by-default lookup) (2025-10-25T13:44:22.000Z)
- [x] T0216 NF middleware/rbac_enforcer.py (FastAPI dependency to enforce matrix, emits audit on deny) (2025-10-25T13:44:22.000Z)
- [x] T0217 NF docs/permissions_matrix.md (roles x endpoints/actions table and RBAC acceptance criteria for FR-017) (2025-10-26T14:42:19.332Z)
- [x] T0214 NF Phase 2 review: re-evaluate spec analysis & list decisions required for Phase 3 (2025-10-26T14:45:00.000Z)

## Phase 3: Controller Integration (HA + TP-Omada)
### Tests First (HA Integration)
- [x] T0303 [P] US3 tests/unit/integrations/test_ha_client.py (REST API mocking, auth token) (2025-10-26T16:57:00.000Z)
- [x] T0304 [P] US3 tests/unit/integrations/test_ha_poller_60s_interval.py (polling timing) (2025-10-26T17:23:00.000Z)
- [x] T0305 [P] US3 tests/unit/integrations/test_ha_poller_backoff.py (exponential backoff on errors) (2025-10-26T17:23:00.000Z)
- [x] T0306 [P] US3 tests/unit/integrations/test_rental_control_event_processing.py (attribute selection, fallback logic) (2025-10-26T17:23:00.000Z)
- [x] T0307 [P] US3 tests/unit/integrations/test_cleanup_service_retention.py (7-day policy) (2025-10-26T17:23:00.000Z)
- [x] T0308 [P] US3 tests/unit/integrations/test_grace_period_logic.py (voucher extension) (2025-10-26T17:23:00.000Z)
- [x] T0309 [P] NF tests/unit/models/test_ha_integration_config_model.py (auth_attribute, grace_minutes validation) (2025-10-26T17:23:00.000Z)

### Tests First (TP-Omada)
- [x] T0300 [P] US1 tests/contract/tp_omada/test_adapter_error_retry.py (backoff)
- [x] T0301 [P] US1 tests/integration/test_authorize_end_to_end.py
- [x] T0302 [P] US1 tests/integration/test_revoke_end_to_end.py
- [x] T0309a [P] US3 tests/unit/services/test_booking_code_case_insensitive.py (D10: case-insensitive matching) (2025-10-26T16:57:00.000Z)

### Implementation (Models & Migrations)
- [x] T0320 NF core/models/ha_integration_config.py (add auth_attribute, checkout_grace_minutes fields) (2025-10-26T21:22:00.000Z)
- [x] T0321 NF core/models/rental_control_event.py (event cache model) (2025-10-26T21:22:00.000Z)
- [x] T0322 NF alembic/versions/XXX_add_ha_integration_fields.py (migration for D7+D9) (2025-10-26T21:22:00.000Z)
- [x] T0323 NF alembic/versions/XXX_create_rental_control_event_table.py (migration for D8) (2025-10-26T21:22:00.000Z)

### Implementation (HA Integration Services)
- [x] T0324 US3 integrations/ha_client.py (REST client, Supervisor API, httpx) (2025-10-26T16:57:00.000Z)
- [x] T0325 US3 integrations/ha_poller.py (60s polling, exponential backoff, background task) (2025-10-26T17:23:00.000Z)
- [x] T0326 US3 integrations/rental_control_service.py (event processing, auth attribute selection, grace period) (2025-10-26T17:23:00.000Z)
- [x] T0327 NF services/cleanup_service.py (7-day retention, daily 3 AM job, audit logging) (2025-10-26T17:23:00.000Z)
- [x] T0328 US3 services/booking_code_validator.py (D10: case-insensitive lookup, case-sensitive storage/display) (2025-10-26T16:57:00.000Z)

### Implementation (TP-Omada)
- [x] T0310 US1 controllers/tp_omada/base_client.py (HTTP wrapper)
- [x] T0311 US1 controllers/tp_omada/adapter.py (authorize, revoke, update)
- [x] T0312 US1 services/retry_queue_service.py (background retry for controller failures) (2025-10-26T21:22:00.000Z)

### Implementation (API Routes - Backend Only per D11)
- [x] T0329 US3 api/routes/integrations.py (CRUD for HAIntegrationConfig, admin-only) (2025-10-26T21:22:00.000Z)
- [x] T0330 US3 api/routes/booking_authorize.py (POST booking code validation, guest endpoint) (2025-10-26T21:22:00.000Z)

### Implementation (Metrics & Review)
- [x] T0313 NF metrics instrumentation (authorize latency, polling errors, cleanup counts, booking_code validation) (2025-10-26T21:22:00.000Z)
- [x] T0314 NF Phase 3 review: re-evaluate spec analysis & list decisions required for Phase 4 (2025-10-27T12:43:00.000Z)

## Phase 4: Admin Web Interface & Theming (See phase4_decisions.md for D12-D17)
### Tests First
- [x] T0400 [P] US2 tests/integration/test_admin_auth_login_logout.py (2025-10-27T12:10:00.000Z)
- [x] T0401 [P] US2 tests/integration/test_admin_session_csrf.py (D14: double-submit cookie) (2025-10-27T11:14:00.000Z)
- [x] T0401a [P] US2 tests/integration/test_admin_session_timeout.py (D17: idle 30min + absolute 8hr) (2025-10-27T11:14:00.000Z)
- [x] T0402 [P] US2 tests/integration/test_admin_extend_revoke_grant.py (2025-10-27T11:14:00.000Z)
- [x] T0403 [P] US2 tests/integration/test_admin_list_filters.py (2025-10-27T11:14:00.000Z)
- [x] T0404 [P] US3 tests/integration/test_entity_mapping_save_retrieve.py (2025-10-27T11:14:00.000Z)
- [x] T0405 [P] US4 tests/integration/test_initial_admin_bootstrap.py (2025-10-27T11:14:00.000Z)
- [x] T0406 [P] US4 tests/integration/test_add_additional_admin.py (2025-10-27T20:20:00.000Z)
- [x] T0407 [P] NF tests/unit/security/test_argon2_password_hashing.py (D13: OWASP params) (2025-10-27T11:14:00.000Z)

### Implementation (Security & Auth per D12-D14, D17)
- [x] T0410 US4 security/password_hashing.py (D13: argon2-cffi, OWASP params m=65536/t=3/p=4)
- [x] T0411 US4 security/session_middleware.py (D12: HTTP-only session cookies, D17: 30min idle/8hr absolute)
- [x] T0412 US4 security/csrf.py (D14: double-submit cookie, 32-byte token)
- [x] T0413 US2 api/routes/admin_auth.py (login/logout, bootstrap)
- [x] T0413a NF N/A - Tables auto-created via SQLModel.metadata.create_all (AdminSession model) (2025-10-27T19:22:00.000Z)

### Implementation (Admin UI Routes & Templates per D15-D16)
- [x] T0414 US2 api/routes/grants.py (list/extend/revoke) (2025-10-27T19:22:00.000Z)
- [x] T0415 US1 api/routes/vouchers.py (redeem) (2025-10-27T19:22:00.000Z)
- [x] T0416 US3 N/A - Entity mapping handled via existing integrations route (2025-10-27T19:22:00.000Z)
- [x] T0417 NF api/routes/health.py (2025-10-27T19:22:00.000Z)
- [x] T0418 NF web/templates/portal/index.html (D16: CSS variable theming) (2025-10-27T19:22:00.000Z)
- [x] T0419 NF web/templates/admin/dashboard.html (2025-10-27T19:22:00.000Z)
- [x] T0420 NF web/themes/default/theme.css (D15: minimal CSS, no framework) (2025-10-27T19:22:00.000Z)
- [x] T0420a NF N/A - Tables auto-created via SQLModel.metadata.create_all (GuestPortalTheme model) (2025-10-27T19:22:00.000Z)

### Implementation (Phase 3 UI Deferred per D11)
- [x] T0422 US3 web/templates/admin/integrations.html (HA config form: integration_id, auth_attribute dropdown, grace_minutes) (2025-10-27T19:22:00.000Z)
- [x] T0423 US3 web/templates/guest/booking_authorize.html (guest booking code form, D16: themed) (2025-10-27T19:22:00.000Z)
- [x] T0424 US2 web/templates/admin/grants_enhanced.html (show booking identifier, grace period, integration source) (2025-10-27T19:22:00.000Z)
- [x] T0425 US3 api/routes/integrations_ui.py (UI routes for integration config forms) (2025-10-27T19:22:00.000Z)

### Review
- [x] T0421 NF Phase 4 review: re-evaluate spec analysis & list decisions required for Phase 5 (2025-10-27T20:20:00.000Z)

## Phase 5: Guest Portal & Authentication (See phase5_decisions.md for D18-D22)
### Tests First (Authorization & Code Validation)
- [x] T0500 [P] NF tests/unit/services/test_unified_code_detection.py (auto-detect voucher vs booking code format) (2025-10-29T19:03:10.000Z)
- [x] T0501 [P] NF tests/unit/services/test_booking_code_format_validation.py (slot_code, slot_name edge cases per FR-018) (2025-10-29T19:03:10.000Z)
- [x] T0502 [P] NF tests/integration/test_booking_code_lookup_happy_path.py (event 0 & 1, time window validation) (2025-10-29T19:03:10.000Z)
- [x] T0503 [P] NF tests/integration/test_booking_code_not_found.py (404 responses) (2025-10-29T19:03:10.000Z)
- [x] T0504 [P] NF tests/integration/test_booking_code_outside_window.py (410 responses, before start/after end + grace period) (2025-10-29T19:03:10.000Z)
- [x] T0505 [P] NF tests/integration/test_booking_code_duplicate_grant.py (409 responses, idempotency) (2025-10-29T19:03:10.000Z)
- [x] T0506 [P] NF tests/integration/test_booking_code_integration_unavailable.py (deny-by-default when HA unavailable) (2025-10-29T19:03:10.000Z)

### Tests First (Rate Limiting per D20)
- [x] T0507 [P] NF tests/unit/security/test_rate_limiter.py (per-IP tracking, rolling window, cleanup) (2025-10-29T19:03:10.000Z)
- [x] T0508 [P] NF tests/integration/test_rate_limit_enforcement.py (429 responses, Retry-After header) (2025-10-29T19:03:10.000Z)
- [x] T0509 [P] NF tests/integration/test_rate_limit_configurable.py (admin config: attempts, window) (2025-10-29T19:03:10.000Z)

### Tests First (Redirect & Grace Period per D21, D22)
- [x] T0510 [P] NF tests/integration/test_post_auth_redirect_original_destination.py (continue URL preserved) (2025-10-29T19:03:10.000Z)
- [x] T0511 [P] NF tests/integration/test_post_auth_redirect_whitelist.py (prevent open redirect) (2025-10-29T19:03:10.000Z)
- [x] T0512 [P] NF tests/integration/test_post_auth_redirect_fallback.py (admin success URL) (2025-10-29T19:03:10.000Z)
- [x] T0513 [P] NF tests/unit/services/test_checkout_grace_period.py (0-30 min extension, grant expiry) (2025-10-29T19:03:10.000Z)
- [x] T0514 [P] NF tests/integration/test_captive_portal_detection_redirects.py (D18: /generate_204, /connecttest.txt, etc.) (2025-10-29T19:03:10.000Z)

### Tests First (End-to-End Guest Flow)
- [x] T0515 [P] NF tests/integration/test_guest_authorization_flow_voucher.py (direct + redirect access) (2025-10-29T19:03:10.000Z)
- [x] T0516 [P] NF tests/integration/test_guest_authorization_flow_booking.py (direct + redirect access) (2025-10-29T19:03:10.000Z)

### Implementation (Portal Routes & Templates per D18, D19)
- [x] T0520 US1 web/routes/guest_portal.py (D18: /guest/authorize direct access) (2025-10-29T20:26:19.000Z)
- [x] T0521 US1 web/routes/captive_detect.py (D18: detection URL redirects) (2025-10-29T20:26:19.000Z)
- [x] T0522 US1 web/templates/guest/authorize.html (D19: unified input field) (2025-10-29T20:26:19.000Z)
- [x] T0523 US1 web/templates/guest/welcome.html (D21: success page) (2025-10-29T20:26:19.000Z)
- [x] T0524 NF web/templates/guest/error.html (themed error messages) (2025-10-29T20:26:19.000Z)

### Implementation (Security & Rate Limiting per D20)
- [x] T0525 NF security/rate_limiter.py (D20: per-IP, configurable limits, rolling window) (2025-10-29T19:03:10.000Z)
- [x] T0526 NF web/middleware/rate_limit_middleware.py (D20: enforcement, 429 responses) (2025-10-29T19:03:10.000Z)

### Implementation (Authorization Logic)
- [x] T0527 US1 services/unified_code_service.py (D19: auto-detect voucher/booking, case handling) (2025-10-29T19:03:10.000Z)
- [x] T0528 US3 services/booking_code_validator.py (format+window+lookup+grace period, metrics, audit) (2025-10-29T19:03:10.000Z)
- [x] T0529 NF services/redirect_validator.py (D21: whitelist external domains, prevent open redirect) (2025-10-29T19:03:10.000Z)

### Implementation (Models & Config per D21, D22)
- [x] T0530 NF models/portal_config.py (add success_redirect_url, rate_limit_attempts, rate_limit_window_seconds) (2025-10-29T20:26:19.000Z)
- [x] T0531 NF models/ha_integration_config.py (checkout_grace_minutes already added in Phase 3) (2025-10-28T09:28:00.000Z)

### Implementation (Documentation & Review)
- [x] T0532 NF docs/guest_authorization.md (FR-018 details, flows, error matrix, D18-D22 decisions) (2025-10-29T20:26:19.000Z)
- [x] T0533 NF Phase 5 review: re-evaluate spec analysis & list decisions required for Phase 6 (2025-10-30T17:24:00.000Z)

## Phase 6: Performance & Hardening
### Tests First
- [ ] T0600 NF tests/performance/test_redeem_latency.py (benchmark scaffold)
- [ ] T0601 NF tests/performance/test_admin_list_scaling.py
- [ ] T0602 NF tests/integration/test_audit_log_completeness.py

### Implementation / Optimization
- [ ] T0603 NF tests/integration/test_portal_config_endpoints.py (CRUD tests for portal configuration)
- [ ] T0604 NF tests/unit/test_portal_config_validation.py (rate limit bounds, grace period validation)
- [ ] T0610 NF optimize DB indices (voucher.code, access_grant.expiration)
- [ ] T0611 NF add caching layer for frequently read vouchers (optional)
- [ ] T0612 NF api/routes/portal_config.py (GET/PUT endpoints for PortalConfig)
- [ ] T0613 NF web/templates/admin/portal_settings.html (UI for rate limits, grace periods, redirect behavior)
- [ ] T0614 NF finalize performance thresholds documentation
- [ ] T0615 NF Phase 6 review: re-evaluate spec analysis & list decisions required for Phase 7

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
