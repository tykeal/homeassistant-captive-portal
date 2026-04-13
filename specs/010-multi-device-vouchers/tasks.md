# Tasks: Multi-Device Vouchers

**Input**: Design documents from `/specs/010-multi-device-vouchers/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Included — the project constitution mandates TDD (red-green-refactor) for all new logic.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `addon/src/captive_portal/` (monolithic add-on)
- **Tests**: `tests/unit/`, `tests/integration/`
- **Templates**: `addon/src/captive_portal/web/templates/admin/`

---

## Phase 1: Setup (Schema & Migration)

**Purpose**: Add the `max_devices` column to the Voucher model and database, establishing the foundation all user stories depend on.

- [ ] T001 Add `max_devices` field (int, default=1, ge=1) to Voucher model in `addon/src/captive_portal/models/voucher.py`
- [ ] T002 Add `_migrate_voucher_max_devices()` migration function in `addon/src/captive_portal/persistence/database.py` following the existing `_migrate_vlan_allowed_vlans()` pattern (ALTER TABLE voucher ADD COLUMN max_devices INTEGER DEFAULT 1)
- [ ] T003 Register `_migrate_voucher_max_devices()` call in `init_db()` in `addon/src/captive_portal/persistence/database.py`

---

## Phase 2: Foundational (Repository & Exception Infrastructure)

**Purpose**: Core repository methods and exception classes that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 [P] Add `count_active_by_voucher_code(voucher_code: str) -> int` method to `AccessGrantRepository` in `addon/src/captive_portal/persistence/repositories.py` — counts grants with status IN (pending, active) for a given voucher code
- [ ] T005 [P] Add `count_active_by_voucher_codes(codes: list[str]) -> dict[str, int]` batch method to `AccessGrantRepository` in `addon/src/captive_portal/persistence/repositories.py` — returns mapping of voucher_code → active grant count for the admin list page
- [ ] T006 [P] Add `VoucherDeviceLimitError(VoucherRedemptionError)` exception class in `addon/src/captive_portal/services/voucher_service.py` with `__init__(self, code: str, max_devices: int)` signature

**Checkpoint**: Foundation ready — repository queries and exception type available for user story implementation.

---

## Phase 3: User Story 1 — Guest Redeems a Multi-Device Voucher (Priority: P1) 🎯 MVP

**Goal**: A guest can redeem a single voucher code from multiple devices, up to the configured max_devices limit. This is the core value proposition of the feature.

**Independent Test**: Create a multi-device voucher (max_devices=3), redeem from 3 different MACs in sequence — verify each succeeds. Attempt a 4th — verify rejection. Verify duplicate MAC detection returns informative message.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T007 [P] [US1] Add unit tests for `VoucherService.redeem()` multi-device logic in `tests/unit/services/test_voucher_service_redeem.py` — test cases: first device succeeds (sets activated_utc), second device succeeds (grant count < max_devices), Nth device rejected when count >= max_devices, duplicate MAC returns "already authorized" message, revoked grant frees slot for new device
- [ ] T008 [P] [US1] Add unit tests for `count_active_by_voucher_code()` repository method in `tests/unit/persistence/test_repository_active_grant_count.py` — test cases: zero grants, mixed statuses (only pending/active counted), revoked/failed/expired excluded
- [ ] T009 [P] [US1] Add integration test for multi-device redemption flow in `tests/integration/test_guest_authorization_flow_voucher.py` — test cases: sequential redemption of 3 devices on a max_devices=3 voucher, 4th device rejected with device-limit message, duplicate MAC on same voucher returns "already authorized"

### Implementation for User Story 1

- [ ] T010 [US1] Modify `VoucherService.redeem()` in `addon/src/captive_portal/services/voucher_service.py` — after existing duplicate-MAC check, add active grant count check via `AccessGrantRepository.count_active_by_voucher_code()`; raise `VoucherDeviceLimitError` when `active_count >= voucher.max_devices`; update duplicate-device error message to "Your device is already authorized with this code." per FR-008
- [ ] T011 [US1] Update guest portal error handling in `addon/src/captive_portal/api/routes/guest_portal.py` — catch `VoucherDeviceLimitError` and return 410 with detail "This code has reached its maximum number of devices." per contracts/api-changes.md; update existing `VoucherRedemptionError` message for duplicate MAC case. Insert catch block above the existing `except VoucherRedemptionError` handler. Include audit logging matching the existing VoucherRedemptionError pattern before raising HTTPException.

**Checkpoint**: At this point, multi-device redemption works end-to-end for the guest flow. A voucher with max_devices > 1 can be redeemed by multiple devices; max_devices=1 behaves identically to current behavior.

---

## Phase 4: User Story 4 — Backward-Compatible Single-Use Vouchers (Priority: P1)

**Goal**: Existing single-use voucher behavior remains unchanged. Vouchers created before this feature (without max_devices) and new vouchers with default max_devices=1 work exactly as today.

**Independent Test**: Create a voucher with default max_devices=1, redeem with one device, confirm a second device is rejected with the existing "already redeemed" semantics.

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T012 [P] [US4] Add unit test for Voucher model default max_devices in `tests/unit/models/test_voucher_model.py` — verify Voucher() without max_devices kwarg defaults to 1; verify max_devices=0 raises ValidationError; verify max_devices=-1 raises ValidationError
- [ ] T013 [P] [US4] Add unit test for migration backward compat in `tests/unit/persistence/test_migrate_voucher_max_devices.py` — verify `_migrate_voucher_max_devices()` adds column with DEFAULT 1; verify existing rows get max_devices=1; verify idempotent (second call is no-op)
- [ ] T014 [P] [US4] Add integration test for single-use backward compat in `tests/integration/test_guest_authorization_flow_voucher.py` — verify max_devices=1 voucher rejects second device with same behavior as pre-feature; verify voucher status transitions unchanged (UNUSED → ACTIVE on first redeem)

### Implementation for User Story 4

> **NOTE**: No new implementation code needed — backward compatibility is delivered by the default=1 in T001 (model), T002 (migration), and the conditional logic in T010 (redeem). This phase validates that the existing behavior is preserved.

- [ ] T015 [US4] Verify all existing voucher unit tests pass without modification by running `uv run pytest tests/unit/services/test_voucher_service_redeem.py tests/unit/services/test_voucher_service_create.py tests/unit/models/test_voucher_model.py -x -q`
- [ ] T016 [US4] Verify all existing integration tests pass without modification by running `uv run pytest tests/integration/test_guest_authorization_flow_voucher.py tests/integration/test_admin_voucher_bulk_ops.py -x -q`

**Checkpoint**: Backward compatibility validated — single-device vouchers behave identically to pre-feature behavior.

---

## Phase 5: User Story 2 — Admin Creates a Multi-Device Voucher (Priority: P1)

**Goal**: Admins can create vouchers with a configurable max_devices value through the admin UI (individual and bulk) and the API.

**Independent Test**: Navigate to admin voucher creation form, set max_devices=5, create voucher, verify it is persisted with max_devices=5. Bulk-create 10 vouchers with max_devices=3, verify all 10 have correct value.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T017 [P] [US2] Add unit tests for `VoucherService.create()` with max_devices param in `tests/unit/services/test_voucher_service_create.py` — test cases: create with explicit max_devices=5, create without max_devices defaults to 1, create with max_devices=0 raises validation error
- [ ] T018 [P] [US2] Add integration test for admin voucher creation with max_devices in `tests/integration/test_admin_vouchers_page.py` — test cases: create via UI form with max_devices field, verify voucher persisted correctly
- [ ] T019 [P] [US2] Add integration test for bulk-create endpoint in `tests/integration/test_admin_voucher_bulk_ops.py` — test cases: POST to `/admin/vouchers/bulk-create` with count=5, max_devices=3; verify 5 vouchers created each with max_devices=3; verify validation rejects max_devices=0

### Implementation for User Story 2

- [ ] T020 [US2] Modify `VoucherService.create()` in `addon/src/captive_portal/services/voucher_service.py` — add `max_devices: int = 1` parameter; pass it to Voucher model constructor
- [ ] T021 [P] [US2] Add `max_devices` field to `CreateVoucherRequest` and `VoucherResponse` Pydantic models in `addon/src/captive_portal/api/routes/vouchers.py` — `max_devices: int = Field(default=1, ge=1)` on request; `max_devices: int` and `active_devices: int` on response
- [ ] T022 [US2] Update API `create_voucher()` route handler in `addon/src/captive_portal/api/routes/vouchers.py` — pass `request.max_devices` to `VoucherService.create()`; populate `active_devices` in response from grant count
- [ ] T023 [US2] Add `max_devices` number input field to the voucher creation form in `addon/src/captive_portal/web/templates/admin/vouchers.html` — add labeled input with min=1, default=1, placed after existing form fields
- [ ] T024 [US2] Update `create_voucher_ui()` route handler in `addon/src/captive_portal/api/routes/vouchers_ui.py` — read `max_devices` from form data (default=1), pass to `VoucherService.create()`
- [ ] T025 [US2] Add bulk-create endpoint `POST /admin/vouchers/bulk-create` in `addon/src/captive_portal/api/routes/vouchers_ui.py` — accept form fields: csrf_token, count (1-100), duration_minutes, max_devices (default=1), booking_ref, allowed_vlans; create N vouchers via `VoucherService.create()` in loop; redirect to `/admin/vouchers/` with success/error flash message
- [ ] T026 [US2] Add bulk-create form section to `addon/src/captive_portal/web/templates/admin/vouchers.html` — form with count, duration_minutes, max_devices, booking_ref, allowed_vlans fields; POST to `/admin/vouchers/bulk-create` with CSRF token

**Checkpoint**: Admins can create single and multi-device vouchers via UI and API. Bulk creation works with shared max_devices.

---

## Phase 6: User Story 3 — Admin Monitors Multi-Device Voucher Usage (Priority: P2)

**Goal**: Admin voucher list displays device usage ("2/5 devices") for each multi-device voucher, enabling at-a-glance capacity monitoring.

**Independent Test**: Create vouchers with max_devices=1 and max_devices=5, redeem some partially, view admin voucher list — verify correct "N/M devices" display for multi-device and "Redeemed"/"Unredeemed" for single-device.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T027 [P] [US3] Add unit test for `count_active_by_voucher_codes()` batch query in `tests/unit/persistence/test_repository_active_grant_count.py` — test cases: multiple voucher codes with varying grant counts, codes with zero grants excluded from result, empty input returns empty dict
- [ ] T028 [P] [US3] Add integration test for admin voucher list device usage display in `tests/integration/test_admin_vouchers_page.py` — test cases: voucher with max_devices=5 and 2 active grants shows "2/5 devices"; voucher with max_devices=1 redeemed shows "Redeemed"; voucher with max_devices=1 unredeemed shows "Unredeemed"; voucher with max_devices=3 and 0 grants shows "0/3 devices"

### Implementation for User Story 3

- [ ] T029 [US3] Update `get_vouchers()` route handler in `addon/src/captive_portal/api/routes/vouchers_ui.py` — query active grant counts via `AccessGrantRepository.count_active_by_voucher_codes()` for all displayed voucher codes; pass `voucher_device_counts` dict to template context
- [ ] T030 [US3] Update voucher list table in `addon/src/captive_portal/web/templates/admin/vouchers.html` — replace/extend "Redemption" column with "Devices" column; for max_devices=1: display "Redeemed" / "Unredeemed" (backward-compatible); for max_devices > 1: display "N/M devices" format using `voucher_device_counts` context variable
- [ ] T031 [US3] Update `list_vouchers()` API response in `addon/src/captive_portal/api/routes/vouchers.py` — populate `active_devices` field on each `VoucherResponse` using batch grant count query

**Checkpoint**: Admin voucher list displays accurate device usage information. All user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Concurrency safety, full test suite validation, and documentation.

- [ ] T032 [P] Add integration test for concurrent redemption race condition in `tests/integration/test_duplicate_redemption_race.py` — test that when two devices simultaneously attempt to claim the last available slot on a multi-device voucher, exactly one succeeds and the other receives "device limit reached" error (FR-006, SC-003)
- [ ] T033 [P] Add integration test for grant revocation freeing device slot in `tests/integration/test_admin_extend_revoke_grant.py` — revoke one grant on a fully-used multi-device voucher, verify a new device can now redeem (FR-007)
- [ ] T034 Run full test suite validation: `uv run pytest tests/ -x -q` — verify zero regressions across all existing unit and integration tests
- [ ] T034a Verify redemption latency with multi-device voucher stays within 800ms p95 baseline by running `tests/performance/test_redeem_latency.py` — ensures the added active-grant-count query does not regress redemption performance
- [ ] T035 Run static analysis validation: `uv run ruff check addon/src/ tests/ && uv run mypy addon/src/ tests/` — verify all new code passes linting, type checking, and docstring coverage
- [ ] T036 Run quickstart.md validation scenarios from `specs/010-multi-device-vouchers/quickstart.md` — execute the key test commands listed and verify all pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001–T003) — model & migration must exist before repository methods reference them
- **User Story 1 (Phase 3)**: Depends on Phase 2 — needs repository methods and exception class
- **User Story 4 (Phase 4)**: Depends on Phase 1 + Phase 3 — validates backward compat after redeem logic changes
- **User Story 2 (Phase 5)**: Depends on Phase 2 — needs repository and exception infra; can run in parallel with Phase 3
- **User Story 3 (Phase 6)**: Depends on Phase 2 + Phase 5 — needs batch query method and admin create flow
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1) — Guest Redeem**: Can start after Phase 2. No dependencies on other stories.
- **US4 (P1) — Backward Compat**: Depends on US1 (validates redeem logic doesn't break existing behavior).
- **US2 (P1) — Admin Create**: Can start after Phase 2. Independent of US1/US4 (creation is separate from redemption).
- **US3 (P2) — Admin Monitor**: Depends on US2 (admin list page needs create flow to produce vouchers to display). Can start batch query implementation (T029) after Phase 2.

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Repository/model changes before service changes
- Service changes before API/route changes
- Route changes before template changes
- Core implementation before integration validation

### Parallel Opportunities

- **Phase 2**: T004, T005, T006 can all run in parallel (different files/methods)
- **Phase 3 Tests**: T007, T008, T009 can all run in parallel (different test files)
- **Phase 4 Tests**: T012, T013, T014 can all run in parallel (different test files)
- **Phase 5 Tests**: T017, T018, T019 can all run in parallel (different test files)
- **Phase 5 Impl**: T021 can run in parallel with T023–T026 (different files)
- **Phase 6 Tests**: T027, T028 can run in parallel (different test files)
- **Phase 7**: T032, T033 can run in parallel (different integration test files)
- **Cross-story**: US1 (Phase 3) and US2 (Phase 5) can run in parallel after Phase 2

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (TDD — must FAIL before implementation):
Task: "Unit tests for redeem() multi-device logic in tests/unit/services/test_voucher_service_redeem.py"
Task: "Unit tests for count_active_by_voucher_code() in tests/unit/persistence/test_repository_active_grant_count.py"
Task: "Integration test for multi-device redemption in tests/integration/test_guest_authorization_flow_voucher.py"

# Then implement sequentially:
Task: "Modify VoucherService.redeem() in addon/src/captive_portal/services/voucher_service.py"
Task: "Update guest portal error handling in addon/src/captive_portal/api/routes/guest_portal.py"
```

## Parallel Example: User Story 2

```bash
# Launch all US2 tests together:
Task: "Unit tests for create() with max_devices in tests/unit/services/test_voucher_service_create.py"
Task: "Integration test for admin voucher creation in tests/integration/test_admin_vouchers_page.py"
Task: "Integration test for bulk-create in tests/integration/test_admin_voucher_bulk_ops.py"

# Then implement — API models can be done in parallel:
Task: "Add max_devices to CreateVoucherRequest/VoucherResponse in addon/src/captive_portal/api/routes/vouchers.py"
Task: "Add max_devices input to vouchers.html template in addon/src/captive_portal/web/templates/admin/vouchers.html"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 4 Only)

1. Complete Phase 1: Setup (model + migration)
2. Complete Phase 2: Foundational (repository + exception)
3. Complete Phase 3: User Story 1 — Guest Redeem
4. Complete Phase 4: User Story 4 — Backward Compat Validation
5. **STOP and VALIDATE**: Multi-device redemption works; existing behavior preserved
6. Deploy/demo if ready — guests can already use multi-device vouchers (created via API/direct DB)

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 (Guest Redeem) → Test independently → Core value delivered
3. Add US4 (Backward Compat) → Validate no regressions → Safety confirmed
4. Add US2 (Admin Create) → Test independently → Full admin workflow
5. Add US3 (Admin Monitor) → Test independently → Operational visibility
6. Polish → Concurrency safety, full suite, docs → Production-ready

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (Phases 1–2)
2. Once Foundational is done:
   - Developer A: User Story 1 (Guest Redeem) → then User Story 4 (Backward Compat)
   - Developer B: User Story 2 (Admin Create) → then User Story 3 (Admin Monitor)
3. Stories integrate independently; Polish phase as final team effort

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD required by constitution: write tests first, verify they fail, then implement
- Commit after each task with conventional commit format (DCO sign-off, SPDX headers)
- Stop at any checkpoint to validate story independently
- SQLite concurrency for FR-006 is handled by existing transaction isolation — no new locking mechanism needed (per research.md R1)
- No new dependencies required — feature uses existing SQLModel, FastAPI, Jinja2 stack
