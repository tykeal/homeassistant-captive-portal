SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Admin UI Pages

**Input**: Design documents from `/specs/005-admin-ui-pages/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/admin-html-routes.md ✅, research.md ✅, quickstart.md ✅

**Tests**: TDD is mandated by the project constitution (Principle II — NON-NEGOTIABLE) and explicitly required in the plan. Test tasks are included for all user stories.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. User stories map from spec.md priorities: US1=Grants (P1), US2=Dashboard (P2), US3=Vouchers (P3), US4=Logout (P4).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `addon/src/captive_portal/` (existing monolith layout)
- **Templates**: `addon/src/captive_portal/web/templates/admin/`
- **CSS/JS**: `addon/src/captive_portal/web/themes/default/`
- **Tests**: `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Register new route modules and prepare shared infrastructure needed by all stories

- [X] T001 Register dashboard_ui, grants_ui, vouchers_ui, and admin_logout_ui route modules in addon/src/captive_portal/app.py
- [X] T002 [P] Add cache-control headers for `/admin/*` paths in addon/src/captive_portal/web/middleware/security_headers.py (FR-028, R2)
- [X] T003 [P] Add alert styles, empty-state class, and voucher-code-display styles to addon/src/captive_portal/web/themes/default/admin.css

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core service and template updates that MUST be complete before user story routes can function

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational Phase

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T004 [P] Write unit tests for DashboardService.get_stats() and DashboardService.get_recent_activity() in tests/unit/services/test_dashboard_service.py — cover zero-data, normal-data, and boundary cases per FR-002, FR-003, FR-004
- [X] T005 [P] Write integration test for cache-control headers on all `/admin/*` responses in tests/integration/test_admin_cache_headers.py — verify Cache-Control, Pragma, and Expires headers per FR-028

### Implementation for Foundational Phase

- [X] T006 Create DashboardService class in addon/src/captive_portal/services/dashboard_service.py — implement get_stats() returning DashboardStats (active_grants, pending_grants, available_vouchers, integrations counts) and get_recent_activity() returning list of ActivityLogEntry with admin username resolution per R4 and data-model.md
- [X] T007 Update logout form action in addon/src/captive_portal/web/templates/admin/portal_settings.html — change from `{{ rp }}/api/admin/logout` to `{{ rp }}/admin/logout` and remove CSRF hidden input per R7
- [X] T008 [P] Update logout form action in addon/src/captive_portal/web/templates/admin/integrations.html — change from `{{ rp }}/api/admin/logout` to `{{ rp }}/admin/logout` and remove CSRF hidden input per R7

**Checkpoint**: Foundation ready — DashboardService tested, cache-control headers active, logout form actions corrected in existing templates. User story implementation can now begin.

---

## Phase 3: User Story 1 — View Grants and Manage Access (Priority: P1) 🎯 MVP

**Goal**: Enable administrators to view all access grants in a table, filter by status, extend active grants, and revoke active, pending, and expired grants (treating expired revokes as an idempotent-like EXPIRED→REVOKED success) — entirely through the web UI.

**Independent Test**: Navigate to `/admin/grants`, verify table loads with correct columns, filter by status, extend a grant's duration, revoke an active grant, revoke an expired grant and observe EXPIRED→REVOKED without error, and verify feedback messages. All form actions work without JavaScript.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T009 [P] [US1] Write unit tests for GET /admin/grants route handler in tests/unit/routes/test_grants_ui.py — cover grant listing with status recomputation, status filter query param, empty state, success/error flash messages per contract GET /admin/grants
- [X] T010 [P] [US1] Write unit tests for POST /admin/grants/extend/{grant_id} in tests/unit/routes/test_grants_ui.py — cover success redirect (including extending an expired grant reactivating it per data-model EXPIRED→ACTIVE behavior), grant not found, revoked grant error, invalid CSRF, invalid minutes per contract POST /admin/grants/extend. Include structured logging assertions for all error paths in the route handler.
- [X] T011 [P] [US1] Write unit tests for POST /admin/grants/revoke/{grant_id} in tests/unit/routes/test_grants_ui.py — cover success redirect (including idempotent revoke and revoking an expired grant transitioning to REVOKED), grant not found, invalid CSRF per contract POST /admin/grants/revoke
- [X] T012 [P] [US1] Write integration tests for full grants page flow in tests/integration/test_admin_grants_page.py — cover page load with auth redirect, grant table rendering, filter by status, extend action with PRG redirect, revoke action with PRG redirect (including revoking an expired grant and verifying it is shown as REVOKED), empty-state display

### Implementation for User Story 1

- [X] T013 [US1] Implement GET /admin/grants route handler in addon/src/captive_portal/api/routes/grants_ui.py — query AccessGrant with status recomputation at render time, support `status` filter query param, pass grants list with csrf_token and flash messages to template per contract and R5/R10
- [X] T014 [US1] Implement POST /admin/grants/extend/{grant_id} in addon/src/captive_portal/api/routes/grants_ui.py — validate CSRF and minutes (1–1440), call GrantService.extend(), PRG redirect to /admin/grants with success/error query params per contract and R5
- [X] T015 [US1] Implement POST /admin/grants/revoke/{grant_id} in addon/src/captive_portal/api/routes/grants_ui.py — validate CSRF, call GrantService.revoke(), PRG redirect to /admin/grants with success/error query params per contract and R5
- [X] T016 [US1] Update addon/src/captive_portal/web/templates/admin/grants_enhanced.html — add success/error feedback message display, empty-state row when no grants match filter, disable extend/revoke buttons for revoked grants, update logout form action to `{{ rp }}/admin/logout` per R7/R9

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently. An admin can view, filter, extend, and revoke grants through the browser.

---

## Phase 4: User Story 2 — View Dashboard Overview (Priority: P2)

**Goal**: Provide administrators with an at-a-glance dashboard showing summary statistics (active grants, pending grants, available vouchers, integrations) and a recent activity feed.

**Independent Test**: Navigate to `/admin/dashboard`, verify four stats cards display correct counts, recent activity table shows up to 20 entries with timestamp/action/target/admin columns, and zero-data states show `0` counts and "No recent activity" gracefully.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T017 [P] [US2] Write unit tests for GET /admin/dashboard route handler in tests/unit/routes/test_dashboard_ui.py — cover stats display, recent activity feed, empty state (zero counts, no activity), auth redirect per contract GET /admin/dashboard. Include a test case for DashboardService exception handling: mock get_stats() to raise, verify graceful error rendering. Include structured logging assertions for all error paths in the route handler.
- [X] T018 [P] [US2] Write integration tests for full dashboard page flow in tests/integration/test_admin_dashboard_page.py — cover page load with stats cards, activity feed rendering, zero-data graceful display, unauthenticated redirect

### Implementation for User Story 2

- [X] T019 [US2] Implement GET /admin/dashboard route handler in addon/src/captive_portal/api/routes/dashboard_ui.py — call DashboardService.get_stats() and DashboardService.get_recent_activity(), pass stats/recent_logs/csrf_token to template per contract GET /admin/dashboard
- [X] T020 [US2] Update addon/src/captive_portal/web/templates/admin/dashboard.html — add empty-state handling for activity feed ("No recent activity"), ensure stats cards display `0` gracefully, fix activity feed timestamp field to use `log.timestamp`, update logout form action to `{{ rp }}/admin/logout` per R7/R9

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently. Admin can see dashboard overview and manage grants.

---

## Phase 5: User Story 3 — Create and Manage Vouchers (Priority: P3)

**Goal**: Enable administrators to view all vouchers with redemption status, create new vouchers with duration and optional booking reference, and see the generated code prominently displayed.

**Independent Test**: Navigate to `/admin/vouchers`, verify voucher list with code/duration/status/redemption columns, create a new voucher via the form, verify generated code is displayed prominently, and verify empty-state message when no vouchers exist.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T021 [P] [US3] Write unit tests for GET /admin/vouchers route handler in tests/unit/routes/test_vouchers_ui.py — cover voucher listing with derived redemption status (FR-018), empty state, new_code highlight, success/error flash messages per contract GET /admin/vouchers
- [X] T022 [P] [US3] Write unit tests for POST /admin/vouchers/create in tests/unit/routes/test_vouchers_ui.py — cover success with code display, invalid CSRF, invalid duration, optional booking_ref per contract POST /admin/vouchers/create. Include structured logging assertions for all error paths in the route handler.
- [X] T023 [P] [US3] Write integration tests for full vouchers page flow in tests/integration/test_admin_vouchers_page.py — cover page load with auth redirect, voucher list rendering, create voucher via form with PRG redirect, new code prominent display, empty-state display

### Implementation for User Story 3

- [X] T024 [US3] Implement GET /admin/vouchers route handler in addon/src/captive_portal/api/routes/vouchers_ui.py — query Voucher table directly (per R3, no separate API), compute derived redemption status per FR-018, pass vouchers/csrf_token/new_code/flash messages to template per contract GET /admin/vouchers
- [X] T025 [US3] Implement POST /admin/vouchers/create in addon/src/captive_portal/api/routes/vouchers_ui.py — validate CSRF and duration_minutes (1–43200), call VoucherService.create(), PRG redirect to /admin/vouchers with new_code and success query params per contract and R6
- [X] T026 [US3] Create addon/src/captive_portal/web/templates/admin/vouchers.html — voucher creation form (duration_minutes required, booking_ref optional, CSRF token), prominent new-code display section, voucher list table with code/duration/status/redemption/created columns, empty-state message, nav bar with correct logout form per R6/R9/R7

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently. Admin can manage grants, view dashboard, and create/view vouchers.

---

## Phase 6: User Story 4 — Logout Securely (Priority: P4)

**Goal**: Ensure the Logout button terminates the admin session and redirects to the login page, with cache-control headers preventing back-button content leakage.

**Independent Test**: Click Logout from any admin page, verify redirect to login page, verify subsequent admin page access redirects to login, verify browser back button shows no cached content (via cache-control headers).

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T027 [P] [US4] Write unit tests for POST /admin/logout route handler in tests/unit/routes/test_admin_logout_ui.py — cover session destruction with redirect to login, no-session-still-redirects, CSRF-exempt behavior per contract POST /admin/logout and R1
- [X] T028 [P] [US4] Write integration tests for full logout flow in tests/integration/test_admin_logout_flow.py — cover logout redirects to login, post-logout admin page access redirects to login, logout response includes cache-control headers, logout form works without JS

### Implementation for User Story 4

- [X] T029 [US4] Implement POST /admin/logout route handler in addon/src/captive_portal/api/routes/admin_logout_ui.py — invoke existing `/api/admin/auth/logout` endpoint, handle both "session destroyed" and "no active session" as success, redirect 303 to `{root_path}/admin/login`, CSRF-exempt per FR-019 and R1

**Checkpoint**: All four user stories should now be independently functional. Complete admin UI is operational.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, performance testing, and cross-cutting improvements

- [X] T030 [P] Extend performance benchmark for voucher list scaling in tests/performance/test_admin_list_scaling.py — add voucher list benchmark (200 vouchers target) alongside existing grant benchmark per plan.md
- [X] T031 [P] Extend tests/performance/test_admin_list_scaling.py with voucher creation benchmarks — add POST /admin/vouchers/create endpoint benchmark measuring response time under load alongside existing list benchmarks
- [X] T032 [P] Create optional progressive-enhancement JavaScript for grants actions in addon/src/captive_portal/web/themes/default/admin-grants.js — external file only (CSP `script-src 'self'`), gracefully degrades per FR-025/FR-010
- [X] T033 Run full test suite validation per quickstart.md — `uv run pytest tests/ -x -q` and `uv run pytest tests/ --cov=captive_portal --cov-report=term-missing`
- [X] T034 Run lint and type check validation per quickstart.md — `uv run ruff check addon/src/ tests/`, `uv run ruff format --check addon/src/ tests/`, `uv run mypy addon/src/`
- [X] T035 Verify all new source files include SPDX headers per FR-027 — `# SPDX-FileCopyrightText: 2025 Andrew Grimberg` and `# SPDX-License-Identifier: Apache-2.0`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **User Stories (Phases 3–6)**: All depend on Foundational phase completion
  - US1 (Grants, P1) → US2 (Dashboard, P2) → US3 (Vouchers, P3) → US4 (Logout, P4) sequentially in priority order
  - OR in parallel if staffed (all stories are independently testable)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 — Grants (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories
- **User Story 2 — Dashboard (P2)**: Can start after Foundational (Phase 2) — Depends on DashboardService from Phase 2 but not on US1 routes
- **User Story 3 — Vouchers (P3)**: Can start after Foundational (Phase 2) — No dependencies on other stories
- **User Story 4 — Logout (P4)**: Can start after Foundational (Phase 2) — No dependencies on other stories; logout form updates in existing templates are handled in Phase 2

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD — constitution Principle II)
- Route handlers before template updates (templates need route context)
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T002 and T003 (Phase 1) can run in parallel
- T004, T005 (Phase 2 tests) can run in parallel
- T007 and T008 (Phase 2 template logout updates) can run in parallel
- All test tasks within each user story marked [P] can run in parallel
- T009, T010, T011, T012 (US1 tests) — all in parallel
- T017, T018 (US2 tests) — in parallel
- T021, T022, T023 (US3 tests) — all in parallel
- T027, T028 (US4 tests) — in parallel
- T030, T031, T032 (Polish) — all in parallel
- Different user stories can be worked on in parallel by different team members after Phase 2

---

## Parallel Example: User Story 1 (Grants)

```bash
# Launch all tests for User Story 1 together:
Task T009: "Unit tests for GET /admin/grants in tests/unit/routes/test_grants_ui.py"
Task T010: "Unit tests for POST extend in tests/unit/routes/test_grants_ui.py"
Task T011: "Unit tests for POST revoke in tests/unit/routes/test_grants_ui.py"
Task T012: "Integration tests for grants page in tests/integration/test_admin_grants_page.py"

# Then implement sequentially:
Task T013: "GET /admin/grants handler in grants_ui.py"
Task T014: "POST extend handler in grants_ui.py" (same file as T013)
Task T015: "POST revoke handler in grants_ui.py" (same file as T013, T014)
Task T016: "Update grants_enhanced.html template"
```

## Parallel Example: User Story 3 (Vouchers)

```bash
# Launch all tests for User Story 3 together:
Task T021: "Unit tests for GET /admin/vouchers in tests/unit/routes/test_vouchers_ui.py"
Task T022: "Unit tests for POST create in tests/unit/routes/test_vouchers_ui.py"
Task T023: "Integration tests for vouchers page in tests/integration/test_admin_vouchers_page.py"

# Then implement sequentially:
Task T024: "GET /admin/vouchers handler in vouchers_ui.py"
Task T025: "POST create handler in vouchers_ui.py" (same file as T024)
Task T026: "Create vouchers.html template"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T008)
3. Complete Phase 3: User Story 1 — Grants (T009–T016)
4. **STOP and VALIDATE**: Test grants page independently — navigate to `/admin/grants`, filter, extend, revoke
5. Deploy/demo if ready — admin can now manage grants through the UI

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 (Grants) → Test independently → Deploy/Demo (**MVP!**)
3. Add User Story 2 (Dashboard) → Test independently → Deploy/Demo
4. Add User Story 3 (Vouchers) → Test independently → Deploy/Demo
5. Add User Story 4 (Logout) → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Grants) — highest priority
   - Developer B: User Story 2 (Dashboard) — can start simultaneously
   - Developer C: User Story 3 (Vouchers) — can start simultaneously
   - Developer D: User Story 4 (Logout) — can start simultaneously
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD is mandated: write tests first, verify they fail, then implement
- Commit after each task or logical group with DCO sign-off
- Stop at any checkpoint to validate story independently
- All new files require SPDX headers (FR-027)
- All admin responses get cache-control headers (FR-028, added in Phase 1)
- All templates use `{{ rp }}` prefix for ingress root path (FR-024)
- No inline JS permitted — external files only (FR-025)
- Forms must work without JS as primary mechanism (FR-010, FR-015)
