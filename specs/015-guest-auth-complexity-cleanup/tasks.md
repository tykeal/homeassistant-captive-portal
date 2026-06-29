SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Guest Auth Complexity Cleanup

**Input**: Design documents from
`/specs/015-guest-auth-complexity-cleanup/`
**Prerequisites**: spec.md (user stories P1-P3), plan.md, research.md,
data-model.md, quickstart.md, contracts/guest-http-contract.md

**Tests**: TDD is MANDATORY per project constitution §II. This feature is a
behavior-preserving refactor, so the feature-014 guest authorization
characterization suite is the safety net. It must pass on current code before
any production code moves, then pass unchanged after each extraction. Add new
assertions only for a to-be-extracted internal unit that is not already pinned.

**Organization**: Tasks are grouped by phases that preserve the settled order:
verify current behavior first, extract shared authorization orchestration,
reduce helper complexity with frozen internal dataclasses, validate the six
issue #189 findings are gone, then refresh metadata and task status separately.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task supports (US1, US2, US3)
- 🟢 = BASELINE/GREEN characterization · 🔴 = RED helper-boundary test ·
  ♻️ = REFACTOR while keeping tests green
- Include exact file paths in descriptions

## Path Conventions

- **Guest route source**:
  `addon/src/captive_portal/api/routes/guest_portal.py`
- **Guest authorization helpers**:
  `addon/src/captive_portal/api/routes/guest_authorization/`
- **New orchestration target**:
  `addon/src/captive_portal/api/routes/guest_authorization/orchestration.py`
- **Existing context helpers**:
  `addon/src/captive_portal/api/routes/guest_authorization/context.py`
- **Existing booking helpers**:
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py`
- **Existing voucher helpers**:
  `addon/src/captive_portal/api/routes/guest_authorization/vouchers.py`
- **Unit route tests**: `tests/unit/routes/`
- **Security tests**: `tests/unit/security/`
- **Guest integration tests**: `tests/integration/`
- **Test utilities**: `tests/utils/`
- **Complexity baseline**: `.aislop/baseline.json`
- **Out of scope**: `addon/src/captive_portal/api/routes/portal_settings_ui.py`
  and the known `portal_settings_ui.py:110` finding from issue #190

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Start implementation from merged spec and plan artifacts while
confirming live source still matches the complexity findings.

- [x] T001 Create implementation branch `015-guest-auth-complexity-cleanup` from
  `main`; confirm `specs/015-guest-auth-complexity-cleanup/` contains `spec.md`,
  `plan.md`, `research.md`, `data-model.md`, `quickstart.md`,
  `contracts/guest-http-contract.md`, and this `tasks.md`

- [x] T002 [US1] Confirm the live source inventory before edits: verify
  `addon/src/captive_portal/api/routes/guest_portal.py` still owns
  `_handle_get_submission` and `_process_authorization`; verify
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` still
  owns `authorize_booking`, `_create_booking_grant`, and
  `_audit_booking_error`; verify
  `addon/src/captive_portal/api/routes/guest_authorization/vouchers.py` still
  owns `authorize_voucher`; do not touch `portal_settings_ui.py`

- [x] T003 [US2] Record the pre-refactor complexity snapshot in the PR notes:
  `guest_portal.py` line count, `_process_authorization` line count,
  `authorize_booking` line/parameter counts, `_create_booking_grant` parameter
  count, `_audit_booking_error` parameter count, and `authorize_voucher`
  parameter count; do not update `.aislop/baseline.json` yet

---

## Phase 2: Foundational — Characterization First (Blocking)

**Purpose**: Prove the current guest authorization contract is already pinned
before any production movement or signature-reduction refactor.

**⚠️ CRITICAL**: No production code movement may begin until T004 through T006
are complete and T007 is green on unmodified production code.

### Characterization for Current Behavior (BASELINE/GREEN) 🟢

> **Run and extend current-behavior tests FIRST; confirm they pass against
> current code before moving `_handle_get_submission`, `_process_authorization`,
> or helper logic. Do not add intentionally failing new-boundary tests until
> after this green baseline.**

- [x] T004 [US1] Map the feature-014 guest authorization characterization suite
  against `specs/015-guest-auth-complexity-cleanup/quickstart.md`; use existing
  tests in `tests/integration/`, `tests/unit/routes/`, `tests/unit/security/`,
  and `tests/utils/test_guest_portal_characterization.py` as the primary safety
  net and identify only uncovered to-be-extracted units

- [x] T005 [P] [US1] Add missing current-behavior assertions, only if T004 finds
  a real gap, to existing feature-014 files such as
  `tests/integration/test_guest_authorization_flow_voucher.py`,
  `tests/integration/test_guest_authorization_flow_booking.py`,
  `tests/integration/test_guest_portal_form_flow.py`, or
  `tests/unit/routes/test_guest_portal_omada_errors.py`; these assertions must
  pass against unmodified current code and must not duplicate behavior already
  pinned by the characterization suite

- [x] T006 [P] [US1] Confirm no new `# noqa` suppressions are introduced in
  `addon/src/captive_portal/api/routes/guest_portal.py` or
  `addon/src/captive_portal/api/routes/guest_authorization/` while adding
  current-behavior characterization coverage

- [x] T007 [US1] Run the complete guest authorization characterization baseline
  on current code and confirm it is green before any production movement:

  ```bash
  uv run pytest \
    tests/utils/test_guest_portal_characterization.py \
    tests/integration/test_guest_portal_form_flow.py \
    tests/integration/test_guest_portal_full_rendering.py \
    tests/integration/test_guest_authorization_flow_voucher.py \
    tests/integration/test_guest_authorization_flow_booking.py \
    tests/integration/test_guest_external_url.py \
    tests/integration/test_post_auth_redirect_fallback.py \
    tests/integration/test_post_auth_redirect_original_destination.py \
    tests/integration/test_post_auth_redirect_whitelist.py \
    tests/integration/test_guest_security_headers.py \
    tests/integration/test_rate_limit_enforcement.py \
    tests/integration/test_vlan_voucher_authorization.py \
    tests/integration/test_vlan_booking_authorization.py \
    tests/unit/routes/test_guest_authorization_context.py \
    tests/unit/routes/test_guest_authorization_controller.py \
    tests/unit/routes/test_guest_authorization_errors.py \
    tests/unit/routes/test_guest_authorization_form.py \
    tests/unit/routes/test_guest_authorization_redirects.py \
    tests/unit/routes/test_guest_portal_mac_extraction.py \
    tests/unit/routes/test_guest_portal_omada.py \
    tests/unit/routes/test_guest_portal_omada_errors.py \
    tests/unit/routes/test_guest_portal_omada_params.py \
    tests/unit/security/test_hmac_csrf.py \
    tests/unit/security/test_rate_limiter.py
  ```

**Checkpoint**: Characterization evidence is green against the pre-refactor
implementation. New RED tests for planned helper boundaries may now be added,
but production code still must not move until those tests exist.

---

## Phase 3: User Story 1 — Preserve Guest Authorization Behavior (Priority: P1) 🎯 MVP

**Goal**: Move shared GET/POST authorization orchestration into cohesive helper
units while `/guest/authorize`, `/guest/welcome`, `/guest/error`, grants, audit
records, redirects, cookies, security headers, and controller calls stay
behavior-equivalent.

**Independent Test**: Run the unchanged characterization suite after each
extraction and verify byte-for-byte equivalence for all stable outputs.

### Tests for New Helper Boundaries (RED) 🔴

> **Write these focused tests after the current-code baseline is green and
> before implementing the new dataclasses or orchestration boundaries.**

- [x] T008 [P] [US1] Add RED tests for `GuestDecisionContext` in
  `tests/unit/routes/test_guest_authorization_context.py`; assert slots/frozen
  behavior and preservation of `request`, `audit_service`, `client_ip`,
  `mac_address`, and `vid` without changing route parameters (RED 🔴)

- [x] T009 [P] [US1] Create RED tests in
  `tests/unit/routes/test_guest_authorization_bookings.py` for new booking
  parameter objects `BookingGrantInput`, `BookingAuditContext`, and
  `BookingAuditFailure`; assert frozen/slots behavior and the exact values that
  `_create_booking_grant` and `_audit_booking_error` must preserve (RED 🔴)

### Implementation for Authorization Orchestration (GREEN/REFACTOR) 🟢♻️

- [x] T010 [US1] Create
  `addon/src/captive_portal/api/routes/guest_authorization/orchestration.py` with
  SPDX headers, module docstring, typed helper signatures, and imports that do
  not create a cycle with `guest_portal.py`

- [x] T011 [US1] Move `_handle_get_submission` from
  `addon/src/captive_portal/api/routes/guest_portal.py` into
  `addon/src/captive_portal/api/routes/guest_authorization/orchestration.py`;
  pass route dependency-provider callables explicitly so GET submission behavior,
  dependency override behavior, HTTP 503 handling, and Omada query preservation
  remain unchanged (REFACTOR ♻️)

- [x] T012 [US1] Move `_process_authorization` from
  `addon/src/captive_portal/api/routes/guest_portal.py` into
  `addon/src/captive_portal/api/routes/guest_authorization/orchestration.py`;
  keep the FastAPI `handle_authorization` route signature, form/query aliases,
  defaults, status codes, headers, cookies, redirects, audit entries, grants, and
  controller calls unchanged (REFACTOR ♻️)

- [x] T013 [US1] Split the moved `_process_authorization` body into private
  helpers in `guest_authorization/orchestration.py` for
  `_prepare_authorization_flow`, `_dispatch_authorization_decision`,
  `_finalize_controller_authorization`, `_raise_controller_failure`, and
  `_complete_success`; preserve the observable operation order from
  `specs/015-guest-auth-complexity-cleanup/contracts/guest-http-contract.md`
  (REFACTOR ♻️)

- [x] T014 [US1] Keep `guest_portal.py` as route declarations, template setup,
  dependency providers, and thin calls into `guest_authorization/orchestration.py`;
  retain any compatibility wrappers needed by existing tests without adding
  `# noqa`

- [x] T015 [US1] Run the unchanged T007 characterization command after T010
  through T014 and fix only behavior regressions within `guest_portal.py`,
  `guest_authorization/orchestration.py`, existing guest authorization helpers,
  or incorrect new assertions from T008 through T009

**Checkpoint**: Shared authorization orchestration has moved out of
`guest_portal.py` and current guest behavior remains characterized green.

---

## Phase 4: User Story 2 — Clear Helper Complexity Findings (Priority: P2)

**Goal**: Remove the six issue #189 complexity findings by grouping repeated
internal inputs and splitting long helper bodies, without changing route
signatures or the external HTTP contract.

**Independent Test**: The characterization suite remains green and line/
parameter checks show the six named findings are absent.

### Parameter Object Tests and Implementations (RED/GREEN) 🔴🟢

- [x] T016 [US2] Implement `GuestDecisionContext` in
  `addon/src/captive_portal/api/routes/guest_authorization/context.py` as
  `@dataclass(frozen=True, slots=True)` with `request`, `audit_service`,
  `client_ip`, `mac_address`, and `vid`; make T008 pass without changing
  `GuestOmadaParams`, `GuestAuthorizationDependencies`, or route-visible fields
  (GREEN 🟢)

- [x] T017 [US2] Update `authorize_voucher` in
  `addon/src/captive_portal/api/routes/guest_authorization/vouchers.py` to accept
  `validation_result`, `session`, and `decision_context` instead of repeated
  audit/request/client/MAC/VLAN scalars; update call sites in
  `guest_authorization/orchestration.py` while preserving voucher validation,
  redemption, VLAN denial, duplicate-device behavior, grant fields, and audit
  metadata

- [x] T018 [US2] Implement `BookingGrantInput`, `BookingAuditContext`, and
  `BookingAuditFailure` in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` as frozen
  slot dataclasses; make T009 pass while preserving booking identifier casing,
  original submitted code, integration ID, booking windows, and audit values
  (GREEN 🟢)

- [x] T019 [US2] Refactor `_create_booking_grant` in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` to accept
  `session` and `BookingGrantInput`; preserve `floor_to_minute(max(now,
  start_utc))`, `ceil_to_minute(effective_end)`, pending status, MAC address,
  `user_input_code`, `booking_ref`, and `integration_id`

- [x] T020 [US2] Refactor `_audit_booking_error` in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` to accept
  `BookingAuditContext` and `BookingAuditFailure`; preserve actor, action,
  outcome, target type/id behavior, user-agent lookup, client IP, and metadata
  keys/values

- [x] T021 [US2] Refactor `authorize_booking` in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` to accept
  `validation_result`, `session`, and `decision_context`; update call sites in
  `guest_authorization/orchestration.py` without changing integration lookup,
  booking window/grace checks, duplicate-grant detection, VLAN denial, exception
  mapping, grant creation, or audit metadata

- [x] T022 [US2] Split the long `authorize_booking` body in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` into
  cohesive private helpers for integration lookup, VLAN validation/audit, booking
  window preparation, duplicate detection, grant construction, and
  exception-to-HTTP mapping; keep `authorize_booking` at or below 80 lines
  (REFACTOR ♻️)

- [x] T023 [US2] Run focused tests after T016 through T022:
  `uv run pytest tests/unit/routes/test_guest_authorization_context.py
  tests/unit/routes/test_guest_authorization_bookings.py
  tests/integration/test_guest_authorization_flow_voucher.py
  tests/integration/test_guest_authorization_flow_booking.py
  tests/integration/test_vlan_voucher_authorization.py
  tests/integration/test_vlan_booking_authorization.py`

- [x] T024 [US2] Run the unchanged T007 characterization command after helper
  signature reduction and fix only behavior regressions within scoped guest
  authorization files or assertions that were wrong about current behavior

**Checkpoint**: Voucher and booking helper signatures are reduced through
internal frozen dataclasses, long booking logic is split, and guest behavior is
still characterization-green.

---

## Phase 5: User Story 2 — Complexity and Scope Validation (Priority: P2)

**Goal**: Prove the six named findings are gone and no new suppressions or
out-of-scope edits were introduced.

- [x] T025 [US2] Verify `addon/src/captive_portal/api/routes/guest_portal.py` is
  below 400 lines and no longer contains `_process_authorization` or
  `_handle_get_submission` implementations; keep route signatures unchanged

- [x] T026 [US2] Verify `_process_authorization` in
  `addon/src/captive_portal/api/routes/guest_authorization/orchestration.py` is
  at or below 80 lines after extraction and splitting

- [x] T027 [US2] Verify `authorize_booking` in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` is at or
  below 80 lines and has six or fewer parameters

- [x] T028 [US2] Verify `_create_booking_grant` and `_audit_booking_error` in
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` each have
  six or fewer parameters

- [x] T029 [US2] Verify `authorize_voucher` in
  `addon/src/captive_portal/api/routes/guest_authorization/vouchers.py` has six
  or fewer parameters

- [x] T030 [US2] Run targeted linting with
  `uv run ruff check addon/src/captive_portal/api/routes/ tests/unit/routes/`;
  confirm ruff C901 passes and no new `# noqa` suppression exists in
  `guest_portal.py` or `guest_authorization/`

- [x] T031 [US2] Run the staged complexity gate with
  `uv run pre-commit run aislop --all-files` or the repository-equivalent
  `aislop ci --staged`; confirm no active issue #189 findings remain for
  `guest_portal.py`, `_process_authorization`, `authorize_booking`,
  `_create_booking_grant`, `_audit_booking_error`, or `authorize_voucher`; do
  not address or baseline `portal_settings_ui.py:110`

- [x] T032 [US2] Confirm the final implementation diff is limited to
  `addon/src/captive_portal/api/routes/guest_portal.py`,
  `addon/src/captive_portal/api/routes/guest_authorization/`, guest
  authorization tests under `tests/`, `.aislop/baseline.json`, and this task
  file's completion checkboxes

**Checkpoint**: The six guest authorization complexity findings are absent,
route and HTTP contracts are unchanged, and the out-of-scope settings finding is
untouched.

---

## Phase 6: User Story 3 — Improve Future Review Safety (Priority: P3)

**Goal**: Make future guest authorization reviews smaller and safer by ensuring
each extracted unit has focused tests, docstrings, types, and clear behavioral
ownership.

**Independent Test**: A reviewer can map voucher validation, booking validation,
orchestration, controller finalization, redirects, grants, and audit behavior to
a cohesive helper and a characterization or unit test path.

- [x] T033 [P] [US3] Ensure every new or changed source file under
  `addon/src/captive_portal/api/routes/guest_authorization/` has required SPDX
  headers, module docstrings, function/class docstrings, and public type
  annotations required by constitution §I

- [x] T034 [P] [US3] Ensure new or changed tests under `tests/unit/routes/` and
  `tests/integration/` name the protected behavior they cover and fail clearly
  when orchestration, voucher, booking, grant, audit, or controller behavior
  regresses

- [x] T035 [US3] In the implementation PR description, include a concise evidence
  map from extracted helper file to protected behavior and targeted test path;
  do not create unrelated repository documentation files for this evidence

**Checkpoint**: The cleaned-up authorization flow is reviewable by cohesive unit
and protected by targeted tests plus the unchanged feature-014 golden suite.

---

## Phase 7: Polish & Cross-Cutting Validation

**Purpose**: Run targeted gates first, then repository-level gates, without
broadening implementation scope.

- [x] T036 [P] Run targeted guest regression tests from
  `specs/015-guest-auth-complexity-cleanup/quickstart.md`:

  ```bash
  uv run pytest \
    tests/utils/test_guest_portal_characterization.py \
    tests/integration/test_guest_portal_form_flow.py \
    tests/integration/test_guest_portal_full_rendering.py \
    tests/integration/test_guest_authorization_flow_voucher.py \
    tests/integration/test_guest_authorization_flow_booking.py \
    tests/integration/test_guest_external_url.py \
    tests/integration/test_post_auth_redirect_fallback.py \
    tests/integration/test_post_auth_redirect_original_destination.py \
    tests/integration/test_post_auth_redirect_whitelist.py \
    tests/integration/test_guest_security_headers.py \
    tests/integration/test_rate_limit_enforcement.py \
    tests/integration/test_vlan_voucher_authorization.py \
    tests/integration/test_vlan_booking_authorization.py \
    tests/unit/routes/test_guest_authorization_context.py \
    tests/unit/routes/test_guest_authorization_controller.py \
    tests/unit/routes/test_guest_authorization_errors.py \
    tests/unit/routes/test_guest_authorization_form.py \
    tests/unit/routes/test_guest_authorization_redirects.py \
    tests/unit/routes/test_guest_portal_mac_extraction.py \
    tests/unit/routes/test_guest_portal_omada.py \
    tests/unit/routes/test_guest_portal_omada_errors.py \
    tests/unit/routes/test_guest_portal_omada_params.py \
    tests/unit/security/test_hmac_csrf.py \
    tests/unit/security/test_rate_limiter.py
  ```

- [x] T037 [P] Run code quality gates for changed code:
  `uv run ruff check addon/src/captive_portal/api/routes/ tests/`,
  `uv run mypy addon/src/captive_portal`,
  `uv run interrogate -vv --fail-under=100 addon/src/captive_portal tests`, and
  `uv run reuse lint`; fix only issues within the implementation scope

- [x] T038 [P] Run `uv run pre-commit run --all-files` and fix hook failures
  without bypassing hooks; if hooks update files automatically, stage the
  changes and rerun the affected checks

- [x] T039 Run full regression suite `uv run pytest tests/ -v` and confirm no
  guest portal, guest authorization, redirect, security-header, Omada, VLAN,
  CSRF, rate-limiter, or integration regression remains before opening the
  implementation PR

- [x] T040 Refresh `.aislop/baseline.json` after the six issue #189 findings are
  absent, then mark completed checkboxes in
  `specs/015-guest-auth-complexity-cleanup/tasks.md`; commit the baseline refresh
  and task-list checkbox updates together as a separate final documentation
  commit after the functional code commits

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Characterization (Phase 2)**: Depends on Setup completion — BLOCKS all
  production code movement
- **US1 Orchestration Extraction (Phase 3)**: Depends on Phase 2 green baseline
- **US2 Helper Complexity Cleanup (Phase 4)**: Depends on moved orchestration and
  RED tests for new internal dataclasses
- **US2 Complexity Validation (Phase 5)**: Depends on Phase 4 implementation and
  unchanged characterization tests
- **US3 Review Safety (Phase 6)**: Depends on extracted helpers and tests
- **Polish (Phase 7)**: Depends on all desired implementation phases being
  complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Phase 2 and delivers behavior-preserving
  orchestration extraction with golden characterization evidence
- **User Story 2 (P2)**: Starts after US1 extraction because the file/function
  findings are cleared safely by moving orchestration and grouping helper inputs
- **User Story 3 (P3)**: Starts after helper files exist and ensures the result
  remains reviewable and testable

### Within Each Story (TDD Cycle)

1. 🟢 **BASELINE**: Characterization tests pass on current behavior before moves
2. 🔴 **RED**: Dataclass/helper-boundary tests fail before the unit exists
3. 🟢 **GREEN**: Extract or implement the minimum code needed to pass tests
4. ♻️ **REFACTOR**: Simplify while keeping characterization and helper tests green
5. **CI tests MUST pass before manual testing** (constitution §II)

### Parallel Opportunities

- T005-T006 can run in parallel after T004 because they touch current-behavior
  tests or perform read-only suppression checks; T008-T009 can run in parallel
  only after T007 proves the current-code baseline is green
- T010-T014 all update orchestration and `guest_portal.py`; integrate them
  sequentially and run T015 after the extraction slice is complete
- T016 and T018 are independent dataclass implementations after their RED tests;
  T017, T019, T020, T021, and T022 should be integrated carefully because they
  update call sites and booking/voucher helper signatures
- T025-T029 are read-only verification tasks that can run in parallel after T024
- T033-T034 can run in parallel after helper ownership is final
- T036-T038 can run in parallel after implementation is complete; T039-T040 are
  final sequential validation and metadata maintenance

---

## Parallel Example: Characterization Baseline

```text
# BASELINE — Launch independent safety-net tasks in parallel:
Task T004: "Map feature-014 characterization coverage"
Task T005: "Only missing current-behavior assertions"
Task T006: "No new noqa suppressions"

# Gate — run before any RED boundary tests or production movement:
Task T007: "Run characterization baseline on current code"
```

## Parallel Example: Complexity Verification

```text
# After helper refactor and characterization are green:
Task T025: "Verify guest_portal.py is below 400 lines"
Task T026: "Verify moved _process_authorization is <=80 lines"
Task T027: "Verify authorize_booking length and params"
Task T028: "Verify booking helper params"
Task T029: "Verify authorize_voucher params"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Characterization baseline (T004-T007) — green on current
   code before any production movement
3. Complete Phase 3: Orchestration extraction (T010-T015)
4. **STOP and VALIDATE**: Run unchanged characterization; all stable guest
   behavior remains equivalent

### Incremental Delivery

1. Characterization baseline → current behavior pinned
2. Orchestration extraction → `guest_portal.py` becomes thin enough for file-size
   cleanup without route-signature changes
3. Frozen dataclasses → voucher and booking helper signatures fall below the
   parameter limit
4. Booking helper split → `authorize_booking` falls below the function-length
   limit
5. Complexity validation and polish → C901, aislop, pre-commit, CI, and Copilot
   review pass cleanly

### TDD Discipline (Constitution §II)

- The feature-014 characterization suite must pass before refactoring and after
  each extraction slice; do not update expected outputs after cleanup unless the
  original golden was wrong about pre-refactor behavior
- Add new assertions only for behavior not already pinned by feature 014,
  especially new frozen parameter objects and helper boundaries
- Never change route signatures, HTTP contracts, database schemas, controller API
  payloads, or operator configuration for this feature
- Never add new `# noqa` suppressions and never touch
  `addon/src/captive_portal/api/routes/portal_settings_ui.py`
- Keep commits atomic; the `.aislop/baseline.json` refresh and task-list checkbox
  updates are a separate final documentation commit in the implementation PR

---

## Notes

- [P] tasks = different files, no dependency on incomplete tasks
- [Story] labels map to spec user stories for traceability
- Public HTTP query parameters, form fields, aliases, defaults, optionality,
  status codes, headers, cookies, redirects, response bodies, audit entries,
  grants, and controller calls are contract artifacts and must not change
- Normalize only dynamic CSRF tokens, generated grant IDs, cookie values,
  controller grant IDs, timestamps, and audit timestamps in golden tests
- Extracted helpers must stay under
  `addon/src/captive_portal/api/routes/guest_authorization/`; do not introduce
  settings, schema, controller API, or unrelated service-layer changes
- All new source and test files require SPDX headers
- Use `uv` for tests and quality gates; do not add new tooling unless a required
  existing command fails because dependencies are missing
