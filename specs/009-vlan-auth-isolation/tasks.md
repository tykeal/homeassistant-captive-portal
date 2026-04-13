SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: VLAN-Based Authorization Isolation

**Input**: Design documents from `/specs/009-vlan-auth-isolation/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), data-model.md

**Tests**: Tests are included as required by the project constitution (Principle II: TDD is NON-NEGOTIABLE).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Addon source**: `addon/src/captive_portal/`
- **Tests**: `tests/`
- **Templates**: `addon/src/captive_portal/web/templates/admin/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Data model extensions and database migrations that all user stories depend on

- [ ] T001 Add `allowed_vlans` JSON column to `HAIntegrationConfig` model with field validator (1–4094 range, deduplication, sorting) in `addon/src/captive_portal/models/ha_integration_config.py`
- [ ] T002 Add `allowed_vlans` JSON column to `Voucher` model with field validator (1–4094 range, deduplication, sorting) in `addon/src/captive_portal/models/voucher.py`
- [ ] T003 Add `_migrate_integration_allowed_vlans()` migration function in `addon/src/captive_portal/persistence/database.py` and register in `init_db()`
- [ ] T004 Add `_migrate_voucher_allowed_vlans()` migration function in `addon/src/captive_portal/persistence/database.py` and register in `init_db()`
- [ ] T005 Create `VlanValidationResult` dataclass and `VlanValidationService` with `parse_vid()`, `validate_booking_vlan()`, and `validate_voucher_vlan()` methods per contract in `addon/src/captive_portal/services/vlan_validation_service.py`

**Checkpoint**: Data model and core validation service ready — user story implementation can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Unit tests for the core validation service that MUST pass before wiring into authorization flow

**⚠️ CRITICAL**: No route-level integration can begin until this phase validates the service logic

### Tests for Foundational Phase ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL, then verify T005 implementation passes them**

- [ ] T006 [P] Unit tests for `VlanValidationService.parse_vid()` covering None, empty, whitespace, valid int, non-numeric, out-of-range (0, 4095, -1), and float inputs in `tests/unit/services/test_vlan_validation_service.py`
- [ ] T007 [P] Unit tests for `VlanValidationService.validate_booking_vlan()` covering: no VLANs configured (skipped), matching VID (allowed), non-matching VID (vlan_mismatch), missing VID with VLANs configured (missing_vid), multiple allowed VLANs in `tests/unit/services/test_vlan_validation_service.py`
- [ ] T008 [P] Unit tests for `VlanValidationService.validate_voucher_vlan()` covering: None allowlist (skipped/unrestricted), matching VID (allowed), non-matching VID (vlan_mismatch), missing VID with VLANs configured (missing_vid) in `tests/unit/services/test_vlan_validation_service.py`
- [ ] T009 [P] Unit tests for `HAIntegrationConfig.allowed_vlans` field validator covering: None input, empty list, valid VLANs, out-of-range values, duplicate removal, sort ordering in `tests/unit/models/test_ha_integration_config_vlans.py`
- [ ] T010 [P] Unit tests for `Voucher.allowed_vlans` field validator covering: None input, valid VLANs, out-of-range values, duplicate removal, sort ordering in `tests/unit/models/test_voucher_vlans.py`

**Checkpoint**: Foundation ready — all validation logic tested, user story wiring can begin

---

## Phase 3: User Story 1 — VLAN Validation During Booking Authorization (Priority: P1) 🎯 MVP

**Goal**: When a guest submits a booking code, validate the device's VLAN ID against the integration's allowed VLANs. Reject authorization with a vague error on mismatch. Skip validation when no VLANs are configured (backward compatible).

**Independent Test**: Configure one integration with `allowed_vlans=[50]`, attempt authorization with `vid=50` (success) and `vid=51` (403 rejection). Attempt with no VLANs configured (success regardless of VID).

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T011 [P] [US1] Integration test: booking authorization succeeds when device VID matches integration's allowed VLANs in `tests/integration/test_vlan_booking_authorization.py`
- [ ] T012 [P] [US1] Integration test: booking authorization rejected with 403 and vague message when device VID does not match integration's allowed VLANs in `tests/integration/test_vlan_booking_authorization.py`
- [ ] T013 [P] [US1] Integration test: booking authorization rejected when integration has VLANs configured but device VID is missing/empty/malformed in `tests/integration/test_vlan_booking_authorization.py`
- [ ] T014 [P] [US1] Integration test: booking authorization succeeds with multiple allowed VLANs when device VID matches any one of them in `tests/integration/test_vlan_booking_authorization.py`
- [ ] T015 [P] [US1] Integration test: audit log entry includes `vlan_id`, `vlan_allowed_list`, and `vlan_result` fields for booking authorization attempts in `tests/integration/test_vlan_booking_authorization.py`
- [ ] T015a [P] [US1] Integration test: booking code exists in two integrations with different VLAN allowlists; device VID resolves to the correct integration in `tests/integration/test_vlan_booking_authorization.py`

### Implementation for User Story 1

- [ ] T016 [US1] Wire `VlanValidationService` into `handle_authorization()` booking code path — after grant creation (PENDING) and before `_authorize_with_controller()` call. On VLAN mismatch: set grant status to FAILED, log audit with `vlan_mismatch` reason, return 403 with "This code is not valid for your network." in `addon/src/captive_portal/api/routes/guest_portal.py`
- [ ] T017 [US1] Wire `VlanValidationService` into `handle_authorization()` for missing VID case — when integration has VLANs configured but `vid` is missing/invalid, reject with "Unable to identify your network. Please check your connection and try again." in `addon/src/captive_portal/api/routes/guest_portal.py`
- [ ] T018 [US1] Add VLAN validation metadata (`vlan_id`, `vlan_allowed_list`, `vlan_result`) to existing audit log calls in the booking authorization path in `addon/src/captive_portal/api/routes/guest_portal.py`
- [ ] T019 [US1] Handle multi-integration booking code resolution with VLAN — refactor booking code path to query all `HAIntegrationConfig` records, find matching events, and use VLAN as additional discriminator per R8 research decision in `addon/src/captive_portal/api/routes/guest_portal.py`
- [ ] T019a [US1] Refactor: extract `_validate_vlan_or_reject()` helper to encapsulate VLAN validation + audit + 403 response logic, reducing branch count in `handle_authorization()` in `addon/src/captive_portal/api/routes/guest_portal.py`

**Checkpoint**: User Story 1 complete — booking authorization enforces VLAN isolation. Verify with `uv run pytest tests/integration/test_vlan_booking_authorization.py -v`

---

## Phase 4: User Story 4 — Backward Compatibility for Unconfigured Integrations (Priority: P2)

**Goal**: Existing deployments with no VLAN configuration experience zero change in authorization behavior after upgrade. Integrations without `allowed_vlans` skip VLAN validation entirely.

**Independent Test**: Upgrade database (run migrations), verify no `allowed_vlans` columns break existing flows. Authorize with booking codes on integrations with no VLAN config — all pass without VLAN checks.

### Tests for User Story 4 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T020 [P] [US4] Integration test: authorization proceeds normally when integration has no VLANs configured (`allowed_vlans` is None) regardless of device VID in `tests/integration/test_vlan_backward_compatibility.py`
- [ ] T021 [P] [US4] Integration test: authorization proceeds normally when integration has empty VLANs list (`allowed_vlans=[]`) regardless of device VID in `tests/integration/test_vlan_backward_compatibility.py`
- [ ] T022 [P] [US4] Integration test: mixed deployment — configured integration enforces VLANs while unconfigured integration skips VLAN checks in the same system in `tests/integration/test_vlan_backward_compatibility.py`
- [ ] T023 [P] [US4] Integration test: database migration adds `allowed_vlans` column with NULL default to existing rows without data loss in `tests/integration/test_vlan_backward_compatibility.py`
- [ ] T023a [P] [US4] Integration test: active grant remains valid after integration's `allowed_vlans` is changed to exclude the grant's VID in `tests/integration/test_vlan_backward_compatibility.py`

### Implementation for User Story 4

- [ ] T024 [US4] Verify `VlanValidationService` returns `allowed=True, reason="skipped"` for `None` and `[]` allowlists (already implemented in T005 — this task validates the wiring from T016/T017 handles these cases correctly end-to-end) in `addon/src/captive_portal/api/routes/guest_portal.py`

**Checkpoint**: User Story 4 complete — backward compatibility verified. Verify with `uv run pytest tests/integration/test_vlan_backward_compatibility.py -v`

---

## Phase 5: User Story 2 — Admin VLAN Configuration Per Integration (Priority: P2)

**Goal**: Admins can configure VLAN allowlists for each integration via the admin API and UI. VLAN IDs are validated (1–4094), deduplicated, sorted, and persisted.

**Independent Test**: POST/PATCH integration with `allowed_vlans`, verify persistence and correct display on GET. Submit invalid VLAN values and verify 422 rejection.

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T025 [P] [US2] Unit test: `POST /api/integrations` with `allowed_vlans` field creates integration with VLAN allowlist persisted in `tests/unit/routes/test_integrations_vlan_api.py`
- [ ] T026 [P] [US2] Unit test: `PATCH /api/integrations/{id}` with `allowed_vlans` updates the VLAN allowlist; omitting field leaves existing VLANs unchanged in `tests/unit/routes/test_integrations_vlan_api.py`
- [ ] T027 [P] [US2] Unit test: `GET /api/integrations` response includes `allowed_vlans` field for each integration in `tests/unit/routes/test_integrations_vlan_api.py`
- [ ] T028 [P] [US2] Unit test: `POST/PATCH` with invalid VLAN values (negative, 0, 4095, non-integer, text) returns 422 validation error in `tests/unit/routes/test_integrations_vlan_api.py`
- [ ] T029 [P] [US2] Unit test: `POST/PATCH` with duplicate VLAN IDs deduplicates and sorts the stored list in `tests/unit/routes/test_integrations_vlan_api.py`
- [ ] T030 [P] [US2] Unit test: same VLAN ID assigned to multiple integrations is accepted (no cross-integration uniqueness constraint per FR-012) in `tests/unit/routes/test_integrations_vlan_api.py`

### Implementation for User Story 2

- [ ] T031 [US2] Add `allowed_vlans: list[int]` field with Pydantic validator (1–4094 range) to `IntegrationConfigCreate` schema in `addon/src/captive_portal/api/routes/integrations.py`
- [ ] T032 [US2] Add `allowed_vlans: list[int] | None` field to `IntegrationConfigUpdate` schema in `addon/src/captive_portal/api/routes/integrations.py`
- [ ] T033 [US2] Add `allowed_vlans: list[int]` field to `IntegrationConfigResponse` schema (default `[]` for None/null DB values) in `addon/src/captive_portal/api/routes/integrations.py`
- [ ] T034 [US2] Wire `allowed_vlans` into `create_integration()` route handler — pass field to model constructor in `addon/src/captive_portal/api/routes/integrations.py`
- [ ] T035 [US2] Wire `allowed_vlans` into `update_integration()` route handler — update field when provided in PATCH body in `addon/src/captive_portal/api/routes/integrations.py`
- [ ] T036 [US2] Add VLAN configuration audit trail — include `allowed_vlans` in create audit meta, include `allowed_vlans_old`/`allowed_vlans_new` in update audit meta in `addon/src/captive_portal/api/routes/integrations.py`
- [ ] T036a [P] [US2] Unit test: audit log entry for `update_integration` includes `allowed_vlans_old` and `allowed_vlans_new` in meta in `tests/unit/test_admin_integration_audit.py`
- [ ] T037 [US2] Add VLAN configuration UI section to integrations admin page — input field for comma-separated VLAN IDs, display of configured VLANs per integration in `addon/src/captive_portal/web/templates/admin/integrations.html`

**Checkpoint**: User Story 2 complete — admins can configure VLANs via API and UI. Verify with `uv run pytest tests/unit/routes/test_integrations_vlan_api.py -v`

---

## Phase 6: User Story 3 — VLAN Scoping for Voucher-Based Access (Priority: P3)

**Goal**: Vouchers can optionally be restricted to specific VLANs. Unrestricted vouchers continue to work on any VLAN. Each redemption attempt is independently validated.

**Independent Test**: Create a VLAN-restricted voucher (`allowed_vlans=[50]`), attempt redemption from `vid=50` (success) and `vid=52` (403). Create an unrestricted voucher (no `allowed_vlans`), redeem from any VID (success).

### Tests for User Story 3 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T038 [P] [US3] Integration test: unrestricted voucher (no `allowed_vlans`) redeemable from any VLAN — backward compatible in `tests/integration/test_vlan_voucher_authorization.py`
- [ ] T039 [P] [US3] Integration test: VLAN-restricted voucher redeemable from matching VID in `tests/integration/test_vlan_voucher_authorization.py`
- [ ] T040 [P] [US3] Integration test: VLAN-restricted voucher rejected with 403 from non-matching VID in `tests/integration/test_vlan_voucher_authorization.py`
- [ ] T041 [P] [US3] Integration test: VLAN-restricted voucher rejected when device VID is missing in `tests/integration/test_vlan_voucher_authorization.py`
- [ ] T042 [P] [US3] Integration test: multi-use voucher with VLAN restriction — each redemption independently validated (VLAN 50 succeeds, then VLAN 52 rejected) in `tests/integration/test_vlan_voucher_authorization.py`

### Implementation for User Story 3

- [ ] T043 [US3] Wire `VlanValidationService` into `handle_authorization()` voucher code path — after voucher validation/grant creation and before controller authorization. On VLAN mismatch: set grant status to FAILED, log audit with `vlan_mismatch`, return 403 in `addon/src/captive_portal/api/routes/guest_portal.py`
- [ ] T044 [US3] Add `allowed_vlans: list[int] | None` field to `CreateVoucherRequest` schema (default `None`) with Pydantic validator (1–4094 range) in `addon/src/captive_portal/api/routes/vouchers.py`
- [ ] T045 [US3] Add `allowed_vlans: list[int] | None` field to `VoucherResponse` schema in `addon/src/captive_portal/api/routes/vouchers.py`
- [ ] T046 [US3] Wire `allowed_vlans` into `create_voucher()` route handler — pass field to `VoucherService` in `addon/src/captive_portal/api/routes/vouchers.py`
- [ ] T047 [US3] Add VLAN validation metadata to audit log for voucher authorization path in `addon/src/captive_portal/api/routes/guest_portal.py`
- [ ] T048 [US3] Add optional VLAN restriction UI to voucher creation on admin vouchers page in `addon/src/captive_portal/web/templates/admin/vouchers.html`

**Checkpoint**: User Story 3 complete — voucher VLAN scoping functional. Verify with `uv run pytest tests/integration/test_vlan_voucher_authorization.py -v`

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and quality assurance across all stories

- [ ] T049 [P] Run full test suite to verify no regressions: `uv run pytest tests/ -v`
- [ ] T050 [P] Run linting and verify zero errors: `uv run ruff check addon/src/ tests/`
- [ ] T051 [P] Run type checking and verify zero errors: `uv run mypy addon/src/captive_portal`
- [ ] T052 [P] Run docstring coverage check: `uv run interrogate addon/src/captive_portal`
- [ ] T053 Verify SPDX license headers on all new files (`vlan_validation_service.py`, all new test files)
- [ ] T054 Run quickstart.md verification checklist — test all 13 items from the verification checklist in `specs/009-vlan-auth-isolation/quickstart.md`
- [ ] T055 Manual verification: confirm SC-004 (admin VLAN configuration under 1 minute) via quickstart checklist walkthrough — this success criterion is verified manually, not via automated test

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001–T005) — tests validate the service and models
- **User Story 1 (Phase 3)**: Depends on Phase 2 — BLOCKS on validated service logic
- **User Story 4 (Phase 4)**: Depends on Phase 3 — validates backward compatibility of the US1 wiring
- **User Story 2 (Phase 5)**: Depends on Phase 1 (model fields) — can proceed in parallel with Phase 3/4
- **User Story 3 (Phase 6)**: Depends on Phase 1 (model fields) and Phase 3 (guest portal wiring pattern)
- **Polish (Phase 7)**: Depends on all story phases being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Setup + Foundational — core security feature, implements first
- **User Story 4 (P2)**: Depends on User Story 1 — validates that US1 wiring preserves backward compatibility
- **User Story 2 (P2)**: Depends on Setup only — admin API/UI can be built independently of guest portal wiring
- **User Story 3 (P3)**: Depends on Setup + User Story 1 wiring pattern — voucher path mirrors booking path

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models/schemas before service wiring
- Service wiring before route handlers
- Route handlers before UI templates
- Audit logging as part of route handler implementation

### Parallel Opportunities

- T001 and T002 can run in parallel (different model files)
- T003 and T004 can run in parallel (different migration functions, same file but independent)
- T006–T010 can all run in parallel (independent test files)
- T011–T015 can all run in parallel (same test file but independent test cases)
- T020–T023 can all run in parallel (same test file but independent test cases)
- T025–T030 can all run in parallel (same test file but independent test cases)
- T038–T042 can all run in parallel (same test file but independent test cases)
- T031–T033 can run in parallel (different schema classes in same file)
- T049–T053 can all run in parallel (independent verification commands)
- User Story 2 (Phase 5) can start as soon as Phase 1 is complete, in parallel with Phases 3–4

---

## Parallel Example: User Story 1

```bash
# Launch all integration tests for User Story 1 together:
Task: T011 "Integration test: booking auth succeeds with matching VID"
Task: T012 "Integration test: booking auth rejected with non-matching VID"
Task: T013 "Integration test: booking auth rejected with missing VID"
Task: T014 "Integration test: booking auth succeeds with multiple allowed VLANs"
Task: T015 "Integration test: audit log includes VLAN validation fields"
```

## Parallel Example: User Story 2

```bash
# Launch all admin API tests together:
Task: T025 "Unit test: POST creates integration with VLANs"
Task: T026 "Unit test: PATCH updates VLAN allowlist"
Task: T027 "Unit test: GET response includes allowed_vlans"
Task: T028 "Unit test: invalid VLANs return 422"
Task: T029 "Unit test: duplicates deduplicated and sorted"
Task: T030 "Unit test: same VLAN on multiple integrations accepted"

# Then launch schema implementations in parallel:
Task: T031 "Add allowed_vlans to IntegrationConfigCreate"
Task: T032 "Add allowed_vlans to IntegrationConfigUpdate"
Task: T033 "Add allowed_vlans to IntegrationConfigResponse"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (data model + migrations + validation service)
2. Complete Phase 2: Foundational (unit tests pass)
3. Complete Phase 3: User Story 1 (booking VLAN validation)
4. **STOP and VALIDATE**: Test US1 independently — `uv run pytest tests/integration/test_vlan_booking_authorization.py`
5. Deploy if ready — core security feature is operational

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy (MVP! Core VLAN isolation active)
3. Add User Story 4 → Verify backward compat → Confidence for upgrade rollout
4. Add User Story 2 → Admin can configure VLANs via UI → Full self-service
5. Add User Story 3 → Voucher VLAN scoping → Defense-in-depth complete
6. Polish phase → Full suite green, linting clean, docs verified

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup (Phase 1) together
2. Once Setup is done:
   - Developer A: Foundational tests (Phase 2) → User Story 1 (Phase 3) → User Story 4 (Phase 4)
   - Developer B: User Story 2 (Phase 5) — admin API/UI (independent of guest portal)
3. After US1 is complete:
   - Developer A or C: User Story 3 (Phase 6) — mirrors US1 pattern for vouchers
4. All developers: Polish (Phase 7)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- TDD enforced: tests MUST fail before implementing the feature code
- Commit after each task or logical group following Conventional Commits
- Error messages MUST NOT leak VLAN IDs or network topology (FR-004, spec assumption)
- `allowed_vlans` uses `sa_column=Column(JSON)` pattern established by `AuditLog.meta`
- VLAN IDs are IEEE 802.1Q compliant: integers 1–4094
- Stop at any checkpoint to validate the story independently
