SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Voucher Management

**Input**: Design documents from `/specs/007-voucher-management/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Tests**: TDD is MANDATORY per project constitution §II. Every production code task is preceded by a failing test task. Red-Green-Refactor throughout.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `addon/src/captive_portal/` (existing monolith layout)
- **Tests**: `tests/` at repository root (`tests/unit/`, `tests/integration/`)
- **Templates**: `addon/src/captive_portal/web/templates/admin/`
- **Static assets**: `addon/src/captive_portal/web/themes/default/`

---

## Phase 1: Setup

**Purpose**: Feature branch creation and workspace preparation

- [ ] T001 Create feature branch `007-voucher-management` from `main` and verify `uv sync --group dev` succeeds

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared error types and GET route enhancement that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (RED 🔴)

- [ ] T002 [P] Write failing tests for VoucherNotFoundError, VoucherExpiredError, and VoucherRedeemedError error types — verify each is importable from `captive_portal.services.voucher_service`, is an `Exception` subclass, and stores a `code` attribute — in `tests/unit/services/test_voucher_service_revoke.py`
- [ ] T003 [P] Write failing tests for `voucher_actions` context variable in GET `/admin/vouchers/` — verify the route returns a `voucher_actions` dict keyed by voucher code with `.can_revoke` and `.can_delete` boolean fields computed per data-model eligibility rules — in `tests/unit/routes/test_vouchers_ui.py`

### Implementation (GREEN 🟢)

- [ ] T004 [P] Implement `VoucherNotFoundError`, `VoucherExpiredError`, and `VoucherRedeemedError` in `addon/src/captive_portal/services/voucher_service.py` — follow existing `GrantNotFoundError`/`GrantOperationError` pattern from `grant_service.py`; each stores the voucher `code`
- [ ] T005 [P] Add `VoucherActions` NamedTuple (fields: `can_revoke: bool`, `can_delete: bool`) and compute `voucher_actions` dict in GET `/admin/vouchers/` route handler — `can_revoke = status not in {REVOKED, EXPIRED} and now <= expires_utc`; `can_delete = redeemed_count == 0` — pass as template context in `addon/src/captive_portal/api/routes/vouchers_ui.py`

**Checkpoint**: Error types importable, GET route provides `voucher_actions` — user story implementation can now begin

---

## Phase 3: User Story 1 — Revoke a Voucher (Priority: P1) 🎯 MVP

**Goal**: Allow admins to revoke individual vouchers (unused or active, not expired) so leaked or cancelled voucher codes can no longer be redeemed

**Independent Test**: Create a voucher → click revoke on the vouchers page → verify status changes to "revoked" and redemption is rejected at the captive portal

### Tests (RED 🔴)

> **Write these tests FIRST — ensure they FAIL before implementation**

- [ ] T006 [P] [US1] Write failing unit tests for `VoucherService.revoke(code)` in `tests/unit/services/test_voucher_service_revoke.py` — cover: UNUSED→REVOKED success, ACTIVE→REVOKED success, REVOKED→REVOKED idempotent no-op (FR-004), VoucherNotFoundError when code missing, VoucherExpiredError when `now > expires_utc` (FR-005) — service contains business logic only; audit logging is the route handler's responsibility
- [ ] T007 [P] [US1] Write failing unit tests for `POST /admin/vouchers/revoke/{code}` route in `tests/unit/routes/test_vouchers_ui.py` — cover: success redirects with `?success=` message, already-revoked redirects as success (idempotent), not-found redirects with `?error=`, expired redirects with `?error=`, invalid CSRF redirects with `?error=` — follow existing `TestRevokeGrant` pattern from `test_grants_ui.py`
- [ ] T008 [P] [US1] Write failing integration tests for revoke full-page flow in `tests/integration/test_admin_voucher_revoke.py` — cover: create voucher → GET page shows enabled revoke button → POST revoke → GET page shows REVOKED status badge and disabled revoke button; verify expired voucher shows disabled revoke button; verify revoked voucher shows disabled revoke button; verify that redeeming a freshly revoked voucher returns a rejection error (FR-003)

### Implementation (GREEN 🟢)

- [ ] T009 [US1] Implement `VoucherService.revoke(code: str) -> Voucher` in `addon/src/captive_portal/services/voucher_service.py` — fetch via `VoucherRepository.get_by_code()`; raise `VoucherNotFoundError` if missing; return immediately if already REVOKED (idempotent FR-004); raise `VoucherExpiredError` if `now > expires_utc` (FR-005); set `status = VoucherStatus.REVOKED`; commit and return — service contains business logic only; audit logging is the route handler's responsibility per grants pattern (`GrantService.revoke()` does no audit logging)
- [ ] T010 [US1] Implement `POST /admin/vouchers/revoke/{code}` route handler in `addon/src/captive_portal/api/routes/vouchers_ui.py` — validate CSRF; instantiate `VoucherService`; call `await voucher_service.revoke(code)`; catch `VoucherNotFoundError` → redirect `?error=Voucher+not+found`; catch `VoucherExpiredError` → redirect `?error=Cannot+revoke+an+expired+voucher`; on success → call `audit_service.log_admin_action(action="voucher.revoke", target_type="voucher", target_id=code)` then redirect `?success=Voucher+{CODE}+revoked+successfully` — audit logged by route handler after any non-error service return (including idempotent revoke), following `grants_ui.py` revoke route pattern per contracts
- [ ] T011 [US1] Add Actions column with per-row revoke button to `addon/src/captive_portal/web/templates/admin/vouchers.html` — add `<th>Actions</th>` header; add revoke `<button type="submit" formaction="{{ rp }}/admin/vouchers/revoke/{{ voucher.code }}">` disabled when `not voucher_actions[voucher.code].can_revoke` — button lives inside the single bulk `<form>` and uses `formaction` to target the single-revoke endpoint (no nested `<form>` tags, which are invalid HTML); add success/error alert display for `success_message`/`error_message` if not already present — per research R6/R7

**Checkpoint**: Admins can revoke individual vouchers. Revoked vouchers are rejected at redemption. MVP complete.

---

## Phase 4: User Story 2 — Delete a Voucher (Priority: P2)

**Goal**: Allow admins to permanently remove unused vouchers (never redeemed) to keep the voucher list clean; guard against race conditions where a voucher is redeemed between page load and delete action

**Independent Test**: Create a voucher (without redeeming) → click delete → verify voucher is completely removed from the list; verify redeemed vouchers cannot be deleted

### Tests (RED 🔴)

> **Write these tests FIRST — ensure they FAIL before implementation**

- [ ] T012 [P] [US2] Write failing unit tests for `VoucherRepository.delete(code)` and `VoucherService.delete(code)` in `tests/unit/services/test_voucher_service_delete.py` — **Repository tests**: predicate-based `DELETE WHERE code=? AND redeemed_count=0` returns True on success, returns False when redeemed_count > 0, returns False when code not found; **Service tests**: successful delete of UNUSED voucher, successful delete of REVOKED-never-redeemed voucher (FR-009), VoucherNotFoundError when code missing, VoucherRedeemedError when redeemed_count > 0, FR-010 race condition (redeemed between read and delete → `VoucherRedeemedError`), concurrent delete (code vanishes → `VoucherNotFoundError`) — service contains business logic only; audit logging is the route handler's responsibility
- [ ] T013 [P] [US2] Write failing unit tests for `POST /admin/vouchers/delete/{code}` route in `tests/unit/routes/test_vouchers_ui.py` — cover: success redirects with `?success=` message, redeemed redirects with `?error=Cannot+delete...it+has+been+redeemed`, not-found redirects with `?error=Voucher+not+found`, invalid CSRF redirects with `?error=`
- [ ] T014 [P] [US2] Write failing integration tests for delete full-page flow in `tests/integration/test_admin_voucher_delete.py` — cover: create unused voucher → GET page shows enabled delete button → POST delete → GET page no longer lists the voucher; create and redeem voucher → GET page shows disabled delete button; create then revoke (unredeemed) → POST delete → voucher removed

### Implementation (GREEN 🟢)

- [ ] T015 [US2] Implement `VoucherRepository.delete(code: str) -> bool` in `addon/src/captive_portal/persistence/repositories.py` — issue atomic `DELETE FROM voucher WHERE code = :code AND redeemed_count = 0`; check `result.rowcount == 1`; flush on success; return bool — per data-model and research R3/R4
- [ ] T016 [US2] Implement `VoucherService.delete(code: str) -> dict` in `addon/src/captive_portal/services/voucher_service.py` — fetch voucher for not-found check and meta snapshot (`status`, `booking_ref`); raise `VoucherNotFoundError` if missing; optionally pre-check `redeemed_count > 0` → raise `VoucherRedeemedError`; call `repo.delete(code)`; if returns False → re-fetch to disambiguate not-found vs. redeemed race (FR-010); on success return meta dict `{"status_at_delete": ..., "booking_ref": ...}` for the caller (route handler) to pass to audit logging; commit — service contains business logic only; audit logging is the route handler's responsibility per grants pattern
- [ ] T017 [US2] Implement `POST /admin/vouchers/delete/{code}` route handler in `addon/src/captive_portal/api/routes/vouchers_ui.py` — validate CSRF; call `meta = await voucher_service.delete(code)`; catch `VoucherNotFoundError` → redirect `?error=Voucher+not+found`; catch `VoucherRedeemedError` → redirect `?error=Cannot+delete+voucher+{CODE}+—+it+has+been+redeemed`; on success → call `audit_service.log_admin_action(action="voucher.delete", target_type="voucher", target_id=code, meta=meta)` then redirect `?success=Voucher+{CODE}+deleted+successfully` — audit logged by route handler after successful service return, following `grants_ui.py` pattern per contracts
- [ ] T018 [US2] Add per-row delete button to Actions column in `addon/src/captive_portal/web/templates/admin/vouchers.html` — add delete `<button type="submit" formaction="{{ rp }}/admin/vouchers/delete/{{ voucher.code }}" class="btn btn-danger">` disabled when `not voucher_actions[voucher.code].can_delete` — button lives inside the single bulk `<form>` and uses `formaction` to target the single-delete endpoint (no nested `<form>` tags); alongside existing revoke button per research R6/R7

**Checkpoint**: Admins can delete unused vouchers. Redeemed vouchers are protected. Race conditions handled. US1 + US2 both independently functional.

---

## Phase 5: User Story 3 — Bulk Voucher Operations (Priority: P3)

**Goal**: Allow admins to select multiple vouchers and apply revoke or delete in bulk, with a summary of successes and skips for mixed-eligibility selections

**Independent Test**: Create several vouchers in various states → select multiple via checkboxes → click "Revoke Selected" or "Delete Selected" → verify eligible vouchers are processed, ineligible are skipped, and summary message is accurate

### Tests (RED 🔴)

> **Write these tests FIRST — ensure they FAIL before implementation**

- [ ] T019 [P] [US3] Write failing unit tests for `BulkResult` dataclass and bulk summary message formatting in `tests/unit/routes/test_vouchers_ui.py` — cover: all-success message (`"Revoked 5 vouchers successfully"`), partial-success message (`"Revoked 3 vouchers, skipped 2 (1 expired, 1 already revoked)"`), all-skipped message (`"No vouchers revoked — 3 skipped ..."`), delete variant messages — per research R9
- [ ] T020 [US3] Write failing unit tests for `POST /admin/vouchers/bulk-revoke` and `POST /admin/vouchers/bulk-delete` routes in `tests/unit/routes/test_vouchers_ui.py` — **bulk-revoke**: all revoked → success redirect, partial success with expired/already-revoked skips → success redirect with summary, all skipped → error redirect, none selected (FR-016) → error redirect; **bulk-delete**: all deleted → success redirect, partial success with redeemed skips → success redirect with summary, all skipped → error redirect, none selected → error redirect; invalid CSRF for both
- [ ] T021 [P] [US3] Write failing integration tests for bulk operations in `tests/integration/test_admin_voucher_bulk_ops.py` — cover: select 3 unused vouchers → bulk-revoke → all revoked with summary; select mix of unused + expired + revoked → bulk-revoke → partial success summary; select 3 unused → bulk-delete → all removed; select mix of unused + redeemed → bulk-delete → partial success summary; select-all checkbox selects all visible; no selection → error message

### Implementation (GREEN 🟢)

- [ ] T022 [US3] Implement `BulkResult` dataclass (`action: str`, `success_count: int`, `skip_reasons: dict[str, int]`) and `format_bulk_message(result: BulkResult) -> str` helper in `addon/src/captive_portal/api/routes/vouchers_ui.py` — format messages per research R9; URL-encode via `urllib.parse.quote_plus()` for redirect query params
- [ ] T023 [US3] Implement `POST /admin/vouchers/bulk-revoke` route handler in `addon/src/captive_portal/api/routes/vouchers_ui.py` — validate CSRF; extract `codes` list from form; if empty → redirect `?error=No+vouchers+selected` (FR-016); iterate codes: pre-check if already REVOKED → count as skip ("already revoked"), else call `voucher_service.revoke(code)` catching `VoucherExpiredError` → skip ("expired") and `VoucherNotFoundError` → skip ("not found"); for each successful revoke call `audit_service.log_admin_action(action="voucher.revoke", target_type="voucher", target_id=code)`; accumulate `BulkResult`; format message; redirect with `?success=` or `?error=` — per research R5/R9
- [ ] T024 [US3] Implement `POST /admin/vouchers/bulk-delete` route handler in `addon/src/captive_portal/api/routes/vouchers_ui.py` — validate CSRF; extract `codes` list from form; if empty → redirect `?error=No+vouchers+selected` (FR-016); iterate codes: call `meta = voucher_service.delete(code)` catching `VoucherRedeemedError` → skip ("already redeemed") and `VoucherNotFoundError` → skip ("not found"); for each successful delete call `audit_service.log_admin_action(action="voucher.delete", target_type="voucher", target_id=code, meta=meta)`; accumulate `BulkResult`; format message; redirect with `?success=` or `?error=` — per research R5/R9
- [ ] T025 [US3] Add checkbox column, select-all header checkbox, and bulk action bar to `addon/src/captive_portal/web/templates/admin/vouchers.html` — wrap voucher table in `<form id="bulk-form" method="POST">` with CSRF hidden field; add `<th><input type="checkbox" id="select-all"></th>` header; add `<td><input type="checkbox" name="codes" value="{{ voucher.code }}"></td>` per row; add bulk action bar with `<button formaction="{{ rp }}/admin/vouchers/bulk-revoke">Revoke Selected</button>` and `<button formaction="{{ rp }}/admin/vouchers/bulk-delete">Delete Selected</button>` — per-row action buttons (revoke/delete) also use `formaction` on `<button>` elements within the same form (no nested `<form>` tags, which are invalid HTML) — per research R6
- [ ] T026 [US3] Create `addon/src/captive_portal/web/themes/default/admin-vouchers.js` for select-all progressive enhancement — `#select-all` checkbox toggles all `input[name="codes"]` checkboxes; individual checkbox changes update select-all state (checked/indeterminate/unchecked); forms work without JS — add `<script src="{{ rp }}/themes/default/admin-vouchers.js"></script>` to vouchers.html
- [ ] T027 [P] [US3] Add `.bulk-action-bar` and checkbox column styles to `addon/src/captive_portal/web/themes/default/admin.css` — style bulk action bar (sticky/visible, button spacing), checkbox alignment in table cells, disabled button styling consistency

**Checkpoint**: All three user stories independently functional. Admins can revoke, delete, and bulk-operate on vouchers with accurate feedback.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Code quality compliance, full test sweep, and validation against quickstart scenarios

- [ ] T028 [P] Run `uv run ruff check addon/src/ tests/` and `uv run ruff format --check addon/src/ tests/` — fix all lint and format issues in new/modified files
- [ ] T029 [P] Run `uv run mypy addon/src/` in strict mode — resolve all type errors in new/modified files; ensure full type annotations on all new functions, methods, and parameters
- [ ] T030 [P] Run `uv tool run interrogate addon/src/ -v` — ensure 100% docstring coverage on all new/modified modules, classes, and public methods
- [ ] T031 Run `uv run pytest tests/ --cov=captive_portal --cov-report=term-missing -x -q` — verify all tests pass, review coverage for new code paths, ensure no regressions in existing tests
- [ ] T032 [P] Verify SPDX headers (`SPDX-FileCopyrightText: 2025 Andrew Grimberg` / `SPDX-License-Identifier: Apache-2.0`) on all new and modified source files — check `admin-vouchers.js`, `test_voucher_service_revoke.py`, `test_voucher_service_delete.py`, `test_admin_voucher_revoke.py`, `test_admin_voucher_delete.py`, `test_admin_voucher_bulk_ops.py`
- [ ] T033 Run quickstart.md manual validation scenarios — start local server via `uv run uvicorn captive_portal.app:create_app --factory --port 8080`; walk through all 11 manual test steps; verify revoke, delete, bulk-revoke, bulk-delete, and select-all behaviors match acceptance criteria
- [ ] T034 [P] Extend `tests/performance/test_admin_list_scaling.py` with benchmarks for voucher management operations — single revoke (<3 s, SC-001), single delete (<3 s, SC-002), and bulk-revoke-20 (<10 s, SC-003); follow existing grant benchmark patterns in the same file

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup ──────────────────────────────────────────────────┐
                                                                  │
Phase 2: Foundational (error types + VoucherActions) ◄────────────┘
         ⚠️ BLOCKS all user stories                   │
                                                       │
     ┌─────────────────────┬───────────────────────────┘
     │                     │                     │
     ▼                     ▼                     ▼
Phase 3: US1 Revoke  Phase 4: US2 Delete   Phase 5: US3 Bulk
  (P1, MVP)            (P2)                  (P3, needs US1+US2)
     │                     │                     │
     └─────────────────────┴─────────────────────┘
                           │
                           ▼
                  Phase 6: Polish
```

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2 only — no dependencies on other stories
- **User Story 2 (P2)**: Depends on Phase 2 only — no dependencies on other stories (can run in parallel with US1 if staffed)
- **User Story 3 (P3)**: Depends on Phase 2 + US1 revoke route + US2 delete route (bulk operations call the single-operation service methods)

### Within Each User Story (TDD Flow)

1. **RED**: Write all failing tests first (unit + route + integration) — tests in different files can be parallel
2. **GREEN**: Implement production code to make tests pass — service → route → template (sequential dependency chain)
3. **Refactor**: Clean up while keeping tests green
4. **Lint**: `uv run ruff check` + `uv run mypy` + `uv run interrogate`
5. **Commit**: `git commit -s -m "feat(vouchers): Description"` — one logical change per commit

### Parallel Opportunities

**Within Phase 2 (RED)**:
- T002 ‖ T003 (different test files)

**Within Phase 2 (GREEN)**:
- T004 ‖ T005 (different source files)

**Within Phase 3 US1 (RED)**:
- T006 ‖ T007 ‖ T008 (all different test files)

**Within Phase 4 US2 (RED)**:
- T012 ‖ T013 ‖ T014 (all different test files)

**Within Phase 5 US3 (RED)**:
- T019 → T020 (same file, sequential)
- T021 ‖ T019 (different files)

**Within Phase 6 (Polish)**:
- T028 ‖ T029 ‖ T030 ‖ T032 (independent quality checks)

**Cross-Story (if team capacity allows)**:
- US1 and US2 can proceed in parallel after Phase 2 (different service methods, different route handlers, different test files)
- US3 must wait for both US1 and US2 GREEN to complete (bulk routes call single-operation services)

---

## Parallel Example: User Story 1

```bash
# Launch all RED tests for US1 together (different files):
Task T006: "Unit tests for VoucherService.revoke() in tests/unit/services/test_voucher_service_revoke.py"
Task T007: "Unit tests for POST revoke route in tests/unit/routes/test_vouchers_ui.py"
Task T008: "Integration tests for revoke flow in tests/integration/test_admin_voucher_revoke.py"

# Then GREEN sequentially (dependency chain):
Task T009: "Implement VoucherService.revoke() in addon/src/.../voucher_service.py"
Task T010: "Implement POST revoke route in addon/src/.../vouchers_ui.py"       # needs T009
Task T011: "Add revoke button to vouchers.html template"                        # needs T010
```

## Parallel Example: User Story 2

```bash
# Launch all RED tests for US2 together (different files):
Task T012: "Unit tests for repo.delete() + service.delete() in tests/unit/services/test_voucher_service_delete.py"
Task T013: "Unit tests for POST delete route in tests/unit/routes/test_vouchers_ui.py"
Task T014: "Integration tests for delete flow in tests/integration/test_admin_voucher_delete.py"

# Then GREEN sequentially (dependency chain):
Task T015: "Implement VoucherRepository.delete() in addon/src/.../repositories.py"
Task T016: "Implement VoucherService.delete() in addon/src/.../voucher_service.py"  # needs T015
Task T017: "Implement POST delete route in addon/src/.../vouchers_ui.py"             # needs T016
Task T018: "Add delete button to vouchers.html template"                              # needs T017
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (branch creation)
2. Complete Phase 2: Foundational (error types + VoucherActions)
3. Complete Phase 3: User Story 1 — Revoke
4. **STOP and VALIDATE**: Run `uv run pytest tests/ -x -q` — all revoke tests pass; manually test revoke on vouchers page
5. Deploy/demo if ready — admins can already revoke compromised vouchers

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 (Revoke) → Test independently → **MVP!** (security control in place)
3. Add User Story 2 (Delete) → Test independently → Housekeeping capability added
4. Add User Story 3 (Bulk Ops) → Test independently → Productivity enhancement added
5. Polish → Full compliance sweep → Feature complete
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Revoke)
   - Developer B: User Story 2 (Delete)
3. Once US1 + US2 complete:
   - Developer A or B: User Story 3 (Bulk Ops)
4. Full team: Polish phase

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in same phase
- [US*] label maps task to specific user story for traceability
- Each user story is independently completable and testable (except US3 depends on US1+US2 service methods)
- RED tests MUST fail before GREEN implementation begins — verify with `uv run pytest <test_file> -x` returning failures
- Commit after each task or logical RED→GREEN pair — use `git commit -s -m "feat(vouchers): ..."` with DCO sign-off
- Stop at any checkpoint to validate story independently
- All redirect URLs must include `request.scope.get("root_path", "")` prefix for ingress compatibility
- CSRF validation uses existing double-submit cookie pattern (`secrets.compare_digest`)
- Audit logging: one entry per individual voucher operation (not per bulk batch) for granular traceability
