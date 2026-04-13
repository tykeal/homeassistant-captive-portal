# Tasks: Voucher Auto-Purge and Admin Purge

**Input**: Design documents from `/specs/011-voucher-purge/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: TDD is NON-NEGOTIABLE per project constitution. Each production task MUST be preceded by its relevant failing unit test(s). Integration and performance tests may be introduced in the phase where their prerequisites become available.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. User Story 3 (timestamp tracking) is in the Foundational phase since it is a blocking prerequisite for all purge operations. User Story 4 (associated data handling) is integrated into Phase 3 alongside User Story 1 because grant nullification is an integral part of the purge operation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US4)
- Exact file paths included in descriptions

## Path Conventions

- **Source**: `addon/src/captive_portal/`
- **Tests**: `tests/`

---

## Phase 1: Setup

**Purpose**: No new project setup required — this feature builds on the existing captive portal codebase. All dependencies, linting, and test infrastructure are already in place.

*No tasks in this phase.*

---

## Phase 2: Foundational (Status Transition Timestamp Tracking)

**Purpose**: Add the `status_changed_utc` timestamp field to the Voucher model, migrate and backfill existing data, and set the timestamp on status transitions. This corresponds to User Story 3 (P1) and is a blocking prerequisite for all purge operations (US1, US2, US4).

**⚠️ CRITICAL**: No purge work (Phase 3 or Phase 4) can begin until this phase is complete.

### Tests (write FIRST, must FAIL before implementation)

- [ ] T001 [P] Write unit tests for `status_changed_utc` field: default value is `None`, field present on model, nullable datetime type, and field included in schema — in `tests/unit/models/test_voucher_model.py`
- [ ] T002 [P] Write unit tests for `_migrate_voucher_status_changed_utc()`: column addition when missing, EXPIRED backfill via `activated_utc + duration_minutes`, EXPIRED fallback via `created_utc + duration_minutes` when `activated_utc` is NULL, REVOKED backfill via migration timestamp, UNUSED/ACTIVE left as NULL, and idempotent re-run safety — in `tests/unit/persistence/test_migrate_voucher_status_changed.py`
- [ ] T003 [P] Write unit tests for `status_changed_utc` timestamp on expire: set to current UTC on ACTIVE→EXPIRED transition via `expire_stale_vouchers()`, NOT overwritten when re-processing already-EXPIRED vouchers (idempotent), and remains NULL for UNUSED/ACTIVE vouchers — in `tests/unit/services/test_voucher_service_expire.py`
- [ ] T004 [P] Write unit tests for `status_changed_utc` timestamp on revoke: set to current UTC on UNUSED→REVOKED and ACTIVE→REVOKED transitions via `revoke()`, set to current UTC on ACTIVE→EXPIRED transition when `revoke()` encounters an already-expired ACTIVE voucher, and NOT overwritten when voucher is already REVOKED — in `tests/unit/services/test_voucher_service_revoke.py`

### Implementation

- [ ] T005 Add `status_changed_utc: Optional[datetime] = Field(default=None)` field to the `Voucher` SQLModel class in `addon/src/captive_portal/models/voucher.py`
- [ ] T006 [P] Implement `_migrate_voucher_status_changed_utc(engine)` migration function in `addon/src/captive_portal/persistence/database.py`: inspect columns, `ALTER TABLE voucher ADD COLUMN status_changed_utc DATETIME`, backfill EXPIRED vouchers via `activated_utc + duration_minutes` (fallback: `created_utc + duration_minutes`), backfill REVOKED vouchers via migration execution timestamp; wire into `init_db()` after `_migrate_voucher_max_devices()`
- [ ] T007 [P] Update `expire_stale_vouchers()` in `addon/src/captive_portal/services/voucher_service.py` to set `status_changed_utc = datetime.now(timezone.utc)` only when transitioning ACTIVE→EXPIRED; skip update if voucher is already EXPIRED (idempotent protection per data-model.md transition rule 5)
- [ ] T008 Update `revoke()` in `addon/src/captive_portal/services/voucher_service.py` to set `status_changed_utc = datetime.now(timezone.utc)` on UNUSED→REVOKED and ACTIVE→REVOKED transitions and on the ACTIVE→EXPIRED branch (already-expired ACTIVE voucher); skip update if voucher is already REVOKED (idempotent protection per data-model.md transition rule 6)

**Checkpoint**: Voucher model tracks when terminal status was reached. Migration backfills all existing data. Ready for purge implementation.

---

## Phase 3: User Story 1 — Automatic Cleanup of Old Vouchers (P1) & User Story 4 — Associated Data Handling (P2) 🎯 MVP

**Goal**: Automatically delete EXPIRED/REVOKED vouchers older than 30 days on admin page load, with proper handling of associated access grants (nullify voucher reference before deletion) and audit trail logging.

**Independent Test**: Create vouchers, transition to EXPIRED/REVOKED, advance time past the 30-day retention window, load the admin voucher page, verify the vouchers are deleted from the database, associated grants are preserved with `voucher_code = NULL`, audit log entries are unchanged, and a new audit entry with action `voucher.auto_purge` is created.

### Tests (write FIRST, must FAIL before implementation)

- [ ] T009 [P] [US1] Write unit tests for `VoucherRepository.count_purgeable(cutoff)`, `VoucherRepository.get_purgeable_codes(cutoff)`, and `VoucherRepository.purge(cutoff)`: correct count of EXPIRED/REVOKED vouchers past cutoff, correct list of purgeable codes, correct deletion count, preservation of UNUSED/ACTIVE vouchers regardless of age, preservation of terminal vouchers within retention period, zero-result case returns 0, and idempotent re-run — in `tests/unit/persistence/test_repository_voucher_purge.py`
- [ ] T010 [P] [US4] Write unit tests for `AccessGrantRepository.nullify_voucher_references(voucher_codes)`: sets `voucher_code = NULL` for matching grants, preserves grants with unrelated voucher codes, handles empty list input gracefully, and returns count of updated grants — in `tests/unit/persistence/test_repository_grant_nullify.py`
- [ ] T011 [P] [US1] Write unit tests for `VoucherPurgeService`: `auto_purge()` uses 30-day retention cutoff, calls `nullify_voucher_references()` before `purge()`, creates audit entry with action `voucher.auto_purge` / actor `system` / meta containing `purged_count` + `retention_days` + `cutoff_utc`, skips audit entry when zero vouchers purged, verifies `manual_purge(min_age_days=0)` purges all terminal vouchers regardless of age (including boundary-timestamp vouchers), and handles concurrent-safe behavior (no errors on double-purge) — in `tests/unit/services/test_voucher_purge_service.py`
- [ ] T012 [P] [US1] Write integration tests for auto-purge on admin page load: auto-purge runs after `expire_stale_vouchers()`, eligible vouchers (>30 days terminal) are deleted, non-eligible vouchers remain, page renders successfully after purge, grants for purged vouchers have `voucher_code = NULL`, pre-existing audit log entries remain unchanged after purge operations (FR-012), and integration test simulating overlapping auto-purge and manual purge targeting same vouchers (FR-014 concurrent safety) — in `tests/integration/test_admin_vouchers_page.py`

### Implementation

- [ ] T013 [US1] Add `count_purgeable(cutoff: datetime | None) -> int`, `get_purgeable_codes(cutoff: datetime | None) -> list[str]`, and `purge(cutoff: datetime | None) -> int` methods to `VoucherRepository` using batch SQL for age-based purge (`cutoff` provided): `WHERE status IN ('expired', 'revoked') AND status_changed_utc < :cutoff`; when `cutoff` is None (manual purge N=0), use an all-terminal-vouchers path without the timestamp filter — in `addon/src/captive_portal/persistence/repositories.py`
- [ ] T014 [US4] Add `nullify_voucher_references(voucher_codes: list[str]) -> int` method to `AccessGrantRepository` using batch SQL: `UPDATE accessgrant SET voucher_code = NULL WHERE voucher_code IN (...)` — in `addon/src/captive_portal/persistence/repositories.py`
- [ ] T015 [US1] Create `VoucherPurgeService` class in `addon/src/captive_portal/services/voucher_purge_service.py` with: `__init__(voucher_repo, grant_repo, audit_service, retention_days=30)`, `async def auto_purge() -> int` (calculates cutoff, queries purgeable codes, nullifies grant references, deletes vouchers, awaits audit logging, returns purged count), `async def count_purgeable(min_age_days: int) -> int`, and `async def manual_purge(min_age_days: int, actor: str) -> int`; `manual_purge` with `min_age_days=0` MUST purge all terminal vouchers regardless of age without relying on `status_changed_utc < cutoff`; include SPDX header and full docstrings
- [ ] T016 [US1] Wire `await voucher_purge_service.auto_purge()` into the async `get_vouchers` GET handler, executing immediately after the existing `expire_stale_vouchers()` call, in `addon/src/captive_portal/api/routes/vouchers_ui.py`; instantiate `VoucherPurgeService` with repository and audit service dependencies

**Checkpoint**: Auto-purge runs on every admin voucher page load. EXPIRED/REVOKED vouchers older than 30 days are automatically cleaned up. Associated grants preserved with nullified voucher references. All operations audited. MVP complete — automatic cleanup alone prevents unbounded database growth.

---

## Phase 4: User Story 2 — Admin Manual Purge of Old Vouchers (P2)

**Goal**: Provide an admin UI form on the vouchers page for on-demand purge with a configurable age threshold (N days, where N=0 means all terminal vouchers), using a two-step preview/confirm flow following the existing Post/Redirect/Get pattern.

**Independent Test**: Navigate to the admin voucher page, enter an age threshold in the purge form, see a confirmation banner with the count of eligible vouchers, confirm the purge, verify the correct vouchers are deleted and a success message is displayed with the purge count.

### Tests (write FIRST, must FAIL before implementation)

- [ ] T017 [P] [US2] Write integration tests for manual purge UI flow: form submission with valid N redirects to preview, preview banner shows correct count and days, confirmation executes purge and redirects with success message, N=0 purges all terminal vouchers, invalid input (negative number, non-integer, empty) redirects with error message, zero-eligible displays info message, CSRF token is validated on both endpoints, audit entry created with action `voucher.manual_purge` and admin username as actor — in `tests/integration/test_admin_voucher_purge.py`

### Implementation

- [ ] T018 [US2] Add "Purge Expired/Revoked Vouchers" form section to the admin voucher template in `addon/src/captive_portal/web/templates/admin/vouchers.html`: `min_age_days` number input field (min=0), CSRF token hidden field, "Preview Purge" submit button posting to `/admin/vouchers/purge-preview`, conditional confirmation banner (rendered when `purge_preview_count` context variable is present) showing count and days with "Confirm Purge" button posting to `/admin/vouchers/purge-confirm` with `min_age_days` as hidden field, and success/error message display
- [ ] T019 [US2] Add `POST /admin/vouchers/purge-preview` endpoint in `addon/src/captive_portal/api/routes/vouchers_ui.py`: validate `min_age_days` form field (parse to non-negative integer, redirect with error on invalid input), call `VoucherPurgeService.count_purgeable(min_age_days)`, redirect to `/admin/vouchers/?purge_preview_count=N&purge_preview_days=D`
- [ ] T020 [US2] Add `POST /admin/vouchers/purge-confirm` endpoint in `addon/src/captive_portal/api/routes/vouchers_ui.py`: validate `min_age_days` form field, call `VoucherPurgeService.manual_purge(min_age_days, actor=admin_username)`, redirect to `/admin/vouchers/?success=Purged+N+vouchers`
- [ ] T021 [US2] Update `get_vouchers` GET handler to extract `purge_preview_count` and `purge_preview_days` query parameters and pass them to the template context for rendering the confirmation banner — in `addon/src/captive_portal/api/routes/vouchers_ui.py`

**Checkpoint**: Admin can perform on-demand purge from the vouchers page. Two-step preview/confirm flow prevents accidental data loss. Complete manual purge workflow executes in under 30 seconds (SC-002). Full feature complete.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, quality checks, and compliance verification across all modified and new files

- [ ] T022 [P] Run full linter suite across all modified and new files: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict`, `uv run interrogate`; fix any violations; verify SPDX headers on all new files (`voucher_purge_service.py`, new test files)
- [ ] T022a [P] Write performance test: batch purge of 10,000 terminal vouchers completes within 10 seconds (SC-003) — in `tests/performance/test_purge_performance.py`
- [ ] T023 Run full test suite with coverage (`uv run pytest --cov=captive_portal --cov-report=term-missing`) and verify all 20 acceptance scenarios from spec.md pass; run quickstart.md manual validation steps (start dev server, navigate to admin vouchers page, test purge form flow)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No tasks — existing project
- **Foundational (Phase 2)**: BLOCKS all user story work — `status_changed_utc` field and migration must be complete
- **US1 + US4 (Phase 3)**: Depends on Phase 2 — uses `status_changed_utc` for age-based purge eligibility
- **US2 (Phase 4)**: Depends on Phase 3 — reuses `VoucherPurgeService.count_purgeable()` and `manual_purge()` methods
- **Polish (Phase 5)**: Depends on all implementation phases being complete

### User Story Dependencies

- **US3 (Foundational)**: No dependencies — provides timestamp tracking needed by all other stories
- **US1 + US4 (Phase 3)**: Depends on US3 — purge eligibility requires `status_changed_utc`
- **US2 (Phase 4)**: Depends on US1 — reuses `VoucherPurgeService` created for auto-purge; adds UI layer on top

### Within Each Phase

- Tests MUST be written and verified to FAIL before implementation begins (TDD red-green-refactor)
- Model/schema changes before repository methods
- Repository methods before service layer
- Service layer before route handlers
- Route handlers before or concurrent with template changes

### Parallel Opportunities

**Phase 2 tests** (all [P] — 4 different files):
```
T001 (model tests)  ║  T002 (migration tests)  ║  T003 (expire tests)  ║  T004 (revoke tests)
```

**Phase 2 implementation** (after T005 completes):
```
T005 (model field)
  ├──→ T006 [P] (migration — database.py)
  └──→ T007 [P] (expire — voucher_service.py)
           └──→ T008 (revoke — same file as T007)
```

**Phase 3 tests** (all [P] — 4 different files):
```
T009 (repo purge)  ║  T010 (repo grant)  ║  T011 (purge service)  ║  T012 (integration)
```

**Phase 3 implementation** (sequential — dependency chain):
```
T013 (repo: VoucherRepository) → T014 (repo: AccessGrantRepository) → T015 (purge service) → T016 (route wiring)
```

**Phase 4** (test first, then sequential implementation):
```
T017 (integration tests) → T018 (template) → T019 (preview endpoint) → T020 (confirm endpoint) → T021 (GET handler)
```

---

## Parallel Example: Phase 3 (US1 + US4)

```bash
# Launch all Phase 3 tests together (4 parallel tasks):
Task T009: "Unit tests for VoucherRepository purge methods in tests/unit/persistence/test_repository_voucher_purge.py"
Task T010: "Unit tests for AccessGrantRepository nullify in tests/unit/persistence/test_repository_grant_nullify.py"
Task T011: "Unit tests for VoucherPurgeService in tests/unit/services/test_voucher_purge_service.py"
Task T012: "Integration tests for auto-purge in tests/integration/test_admin_vouchers_page.py"
```

---

## Implementation Strategy

### MVP First (Phase 2 + Phase 3)

1. Complete Phase 2: Foundational (timestamp tracking + migration)
2. Complete Phase 3: Auto-purge + grant handling
3. **STOP and VALIDATE**: Auto-purge runs on page load, cleans up old vouchers, grants preserved
4. Deploy if ready — automatic cleanup alone delivers the primary value (SC-001)

### Incremental Delivery

1. Phase 2 → Timestamp tracking complete → Vouchers track terminal status age
2. Phase 3 → Auto-purge functional → **MVP deployed** (prevents unbounded DB growth)
3. Phase 4 → Manual purge UI → Full feature with admin control
4. Phase 5 → Quality validation → Release-ready

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- US3 is in Foundational (Phase 2) because it is a prerequisite for all purge operations
- US4 is integrated into Phase 3 alongside US1 — grant nullification is an integral part of the purge delete operation
- TDD is NON-NEGOTIABLE: write tests first, verify they fail, then implement
- SPDX headers required on all new files (per constitution principle V)
- DCO sign-off required on all commits
- Conventional Commits with capitalized types (e.g., `Feat:`, `Test:`, `Refactor:`)
- All code must pass: ruff lint, ruff format, mypy strict, interrogate 100% docstring coverage
- Commit after each task or logical group of tasks
