SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Omada Controller Integration Wiring

**Input**: Design documents from `/specs/008-omada-controller-wiring/`
**Prerequisites**: spec.md (user stories with priorities P1–P4), plan.md, research.md, data-model.md, contracts/controller-adapter.md

**Tests**: TDD is MANDATORY per project constitution §II. Every unit of production code is preceded by a failing test (Red-Green-Refactor). Unit tests precede implementation; integration and contract tests are included in appropriate phases.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- 🔴 = RED (failing test written first) · 🟢 = GREEN (production code makes test pass)
- Include exact file paths in descriptions

## Path Conventions

- **Addon source**: `addon/src/captive_portal/`
- **Addon config**: `addon/config.yaml`
- **Controllers**: `addon/src/captive_portal/controllers/tp_omada/`
- **API routes**: `addon/src/captive_portal/api/routes/`
- **s6 services**: `addon/rootfs/etc/s6-overlay/s6-rc.d/`
- **Tests (unit)**: `tests/unit/`
- **Tests (integration)**: `tests/integration/`
- **Tests (contract)**: `tests/contract/tp_omada/`
- **Documentation**: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch creation

- [ ] T001 Create feature branch `008-omada-controller-wiring` from `main`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration schema, application settings, s6 service scripts, application lifespan wiring, and dependency injection — the shared infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T002 [P] Write failing unit tests for 6 Omada settings fields in `tests/unit/config/test_settings_omada_fields.py` — verify `AppSettings` exposes: `omada_controller_url` (default `""`), `omada_username` (default `""`), `omada_password` (default `""`), `omada_site_name` (default `"Default"`), `omada_controller_id` (default `""`), `omada_verify_ssl` (default `True`); test three-tier resolution for each field: addon option → `CP_OMADA_*` env var → default; test boolean coercion for `omada_verify_ssl` from env var strings `"true"`/`"false"`/`"1"`/`"0"`; test `log_effective()` logs password as `"(set)"`/`"(not set)"` — never the actual value; test Omada is considered "configured" when `omada_controller_url` is non-empty (RED 🔴)

- [ ] T003 [P] Write failing unit tests for admin app lifespan Omada wiring in `tests/unit/test_app_lifespan_omada.py` — test that when Omada settings are configured (`omada_controller_url` non-empty): (a) `app.state.omada_config` is a dict with keys `base_url`, `controller_id`, `username`, `password`, `verify_ssl`, `site_id` (where `omada_site_name` maps to `site_id`), (b) no `OmadaClient` or `OmadaAdapter` instances are stored on `app.state` (per-request creation avoids shared async state races), (c) no network I/O occurs during startup; test that when Omada is NOT configured (empty URL): (d) `app.state.omada_config` is `None`, (e) no errors logged (RED 🔴)

- [ ] T004 [P] Write failing unit tests for guest app lifespan Omada wiring in `tests/unit/test_guest_app_lifespan_omada.py` — same scenarios as T003 but targeting `guest_app.py` lifespan: configured → `omada_config` dict on state, not configured → `None` on state, no startup network I/O; verify guest app stores its own independent config (not shared with admin app) (RED 🔴)

- [ ] T005 [P] Write failing unit test for `get_omada_adapter` dependency function in `tests/unit/controllers/tp_omada/test_omada_dependencies.py` — verify: (a) when `app.state.omada_config` exists with valid config dict, constructs and returns a fresh `OmadaAdapter` wrapping a fresh `OmadaClient` with correct params, (b) when `app.state.omada_config` is `None`, returns `None`, (c) when `omada_config` attribute does not exist on state, returns `None` gracefully (RED 🔴)

### Implementation for Foundational (GREEN) 🟢

- [ ] T006 Add 6 Omada optional fields to addon config schema in `addon/config.yaml` — under `schema:` section add: `omada_controller_url: "url?"`, `omada_username: "str?"`, `omada_password: "password?"`, `omada_site_name: "str?"`, `omada_controller_id: "str?"`, `omada_verify_ssl: "bool?"`; follow the existing pattern for `guest_external_url`, `ha_base_url`, and `ha_token` (GREEN 🟢 — supports T002)

- [ ] T007 Add 6 Omada fields to `AppSettings` in `addon/src/captive_portal/config/settings.py` — add field declarations with defaults per data-model.md (`omada_controller_url: str = ""`, `omada_username: str = ""`, `omada_password: str = ""`, `omada_site_name: str = "Default"`, `omada_controller_id: str = ""`, `omada_verify_ssl: bool = True`); extend `_ADDON_OPTION_MAP` with 6 entries (`"omada_controller_url": "omada_controller_url"`, etc.); extend `_ENV_VAR_MAP` with 6 entries (`"CP_OMADA_CONTROLLER_URL": "omada_controller_url"`, etc.); extend `_validate_field()` to accept Omada fields (`omada_controller_url` as URL, `omada_username`/`omada_password`/`omada_site_name`/`omada_controller_id` as optional strings, `omada_verify_ssl` as bool); extend `_coerce_field()` to trim/coerce Omada string values and coerce env var strings for `omada_verify_ssl` into bool; extend `load()` resolution loop to resolve these fields through the updated validation/coercion path so configured values do not fall back to defaults; extend `log_effective()` to log all 6 fields, with `omada_password` shown as `"(set)"`/`"(not set)"` — never the actual value; add `omada_configured` property that returns `bool(self.omada_controller_url)` (GREEN 🟢 — T002 passes)

- [ ] T008 [P] Export `CP_OMADA_*` environment variables in admin s6 run script `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/run` — before the `exec` line, read 6 Omada options via `bashio::config` with empty-string defaults and export as `CP_OMADA_CONTROLLER_URL`, `CP_OMADA_USERNAME`, `CP_OMADA_PASSWORD`, `CP_OMADA_SITE_NAME`, `CP_OMADA_CONTROLLER_ID`, `CP_OMADA_VERIFY_SSL`; follow the existing pattern used for `log_level` in this file and `guest_external_url` in the guest run script (GREEN 🟢)

- [ ] T009 [P] Export `CP_OMADA_*` environment variables in guest s6 run script `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/run` — same 6 env var exports as T008, following the existing `CP_GUEST_EXTERNAL_URL` pattern in this file; both admin and guest processes need independent access to Omada configuration (GREEN 🟢)

- [ ] T010 Wire Omada controller configuration into admin app lifespan in `addon/src/captive_portal/app.py` — in `_make_lifespan()` startup section: if `settings.omada_controller_url` is non-empty, store an `omada_config` dict on `app.state` containing `base_url=settings.omada_controller_url`, `controller_id=settings.omada_controller_id`, `username=settings.omada_username`, `password=settings.omada_password`, `verify_ssl=settings.omada_verify_ssl`, `site_id=settings.omada_site_name` (note: `omada_site_name` setting maps to adapter's `site_id` parameter); log "OmadaClient configured for {url}"; if URL is empty, set `app.state.omada_config = None` and log info "Omada controller not configured — controller calls will be skipped"; do NOT construct or store a shared `OmadaClient`/`OmadaAdapter` instance — route handlers create fresh instances per request via `get_omada_adapter` to avoid shared async session state races (GREEN 🟢 — T003 passes)

- [ ] T011 Wire Omada controller configuration into guest app lifespan in `addon/src/captive_portal/guest_app.py` — same pattern as T010: store `omada_config` dict on `app.state` when configured, set to `None` when not; keep admin and guest app state independent; log Omada configuration status; do NOT store shared client/adapter instances (GREEN 🟢 — T004 passes)

- [ ] T012 Create `get_omada_adapter` dependency function in `addon/src/captive_portal/controllers/tp_omada/dependencies.py` — function signature `def get_omada_adapter(request: Request) -> OmadaAdapter | None`; read `omada_config = getattr(request.app.state, "omada_config", None)` and return `None` when absent; otherwise construct and return a fresh `OmadaClient(base_url=..., controller_id=..., username=..., password=..., verify_ssl=...)` wrapped in `OmadaAdapter(client=client, site_id=omada_config["site_id"])`; each request gets its own client instance to avoid shared async state races; add SPDX header and docstring; used as `Depends(get_omada_adapter)` in route handlers (GREEN 🟢 — T005 passes)

**Checkpoint**: Foundation ready — configuration, settings, s6 scripts, lifespan wiring, and dependency injection are all in place. User story implementation can now begin.

---

## Phase 3: User Story 1 — Guest WiFi Authorization via Omada Controller (Priority: P1) 🎯 MVP

**Goal**: When a guest submits a valid code on the captive portal, the system creates an access grant AND instructs the Omada controller to authorize the guest's device on the network

**Independent Test**: Submit a valid code on the guest portal, verify the grant transitions PENDING→ACTIVE, the controller receives an authorize call with correct MAC and expiry, and the controller's grant identifier is stored on the grant record

### Tests for User Story 1 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T013 [P] [US1] Write failing unit tests for guest authorization controller wiring in `tests/unit/routes/test_guest_portal_omada.py` — mock `OmadaAdapter` and `OmadaClient`; test: (a) when adapter is configured, `adapter.authorize()` is called within `async with adapter.client:` context with guest's MAC address and `grant.end_utc`, (b) on successful authorize, grant status transitions from PENDING to ACTIVE and `controller_grant_id` is set from response `grant_id`, (c) when adapter is `None` (no controller configured), grant transitions directly PENDING→ACTIVE with no controller call (graceful degradation per FR-013), (d) verify `async with adapter.client:` is used for each operation (per-operation context, not persistent connection per research R1) (RED 🔴)

- [ ] T014 [P] [US1] Write failing unit tests for guest authorization error handling in `tests/unit/routes/test_guest_portal_omada_errors.py` — mock `OmadaAdapter` to raise exceptions; test: (a) on `OmadaClientError`, grant transitions PENDING→FAILED (FR-012), (b) on `OmadaRetryExhaustedError`, grant transitions PENDING→FAILED, (c) user-friendly error message is returned to guest (not raw exception details), (d) failure is recorded in audit log with error details, (e) grant database record is consistent (committed) regardless of controller outcome (RED 🔴)

### Implementation for User Story 1 (GREEN) 🟢

- [ ] T015 [US1] Wire controller authorize call into guest authorization flow — **prerequisite**: add `GrantStatus.FAILED` to `addon/src/captive_portal/models/access_grant.py` enum and update any status recompute/normalization logic so a controller failure state is preserved and not overwritten by derived ACTIVE/EXPIRED transitions; **then** in `addon/src/captive_portal/api/routes/guest_portal.py` after grant creation (PENDING status): access `omada_adapter` via `get_omada_adapter` dependency; if adapter is not `None`: enter `async with adapter.client:` context, call `await adapter.authorize(mac=mac_address, expires_at=grant.end_utc)`, on success update `grant.status = GrantStatus.ACTIVE` and `grant.controller_grant_id = result["grant_id"]`, commit to database; on `OmadaClientError` or `OmadaRetryExhaustedError`: update `grant.status = GrantStatus.FAILED`, log error with structured logging, create audit log entry for failure, return user-friendly error message to guest; if adapter is `None`: set `grant.status = GrantStatus.ACTIVE` directly (existing behavior preserved per FR-013); commit grant status change (GREEN 🟢 — T013, T014 pass)

**Checkpoint**: User Story 1 is fully functional — guest authorization triggers controller wiring when configured, degrades gracefully when not

---

## Phase 4: User Story 2 — Admin Revokes Guest Network Access (Priority: P2)

**Goal**: When an admin revokes a grant, the system updates the database AND instructs the Omada controller to deauthorize the guest's MAC address

**Independent Test**: Create an active grant, revoke it through the admin API, verify the grant status is REVOKED in the database AND the controller receives the revoke call with the correct MAC address

### Tests for User Story 2 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T016 [P] [US2] Write failing unit tests for grant revocation controller wiring in `tests/unit/routes/test_grants_omada.py` — mock `OmadaAdapter` and `OmadaClient`; test: (a) when adapter is configured and grant has MAC, `adapter.revoke(mac)` is called within `async with adapter.client:` context after DB revocation, (b) controller success → revocation complete, (c) controller "already revoked" response → treated as success (idempotent per FR-015), (d) when adapter is `None` → DB-only revocation (FR-017), (e) when grant has no MAC address (legacy grants) → skip controller call, DB-only revocation (FR-018), (f) verify DB grant is always REVOKED regardless of controller outcome (RED 🔴)

- [ ] T017 [P] [US2] Write failing unit tests for revocation error handling in `tests/unit/routes/test_grants_omada_errors.py` — mock `OmadaAdapter` to raise exceptions; test: (a) on `OmadaClientError`, DB grant stays REVOKED (FR-016), error is logged, (b) admin response includes partial failure notification ("database updated, controller revocation may need manual attention"), (c) audit log records both DB revocation and controller failure, (d) on `OmadaRetryExhaustedError`, same behavior as `OmadaClientError` (RED 🔴)

### Implementation for User Story 2 (GREEN) 🟢

- [ ] T018 [US2] Wire controller revoke call into grant revocation flow in `addon/src/captive_portal/api/routes/grants.py` — in revoke endpoint, after `grant_service.revoke()` succeeds (DB status = REVOKED): access `omada_adapter` via `get_omada_adapter` dependency or `request.app.state`; if adapter is not `None` and `grant.mac` is non-empty: enter `async with adapter.client:` context, call `await adapter.revoke(mac=grant.mac)`, on success → revocation complete; on `OmadaClientError` or `OmadaRetryExhaustedError` → log error, add partial-failure warning to admin response, DB grant stays REVOKED; if adapter is `None` or grant has no MAC → DB-only revocation (current behavior preserved); create audit log entry recording revocation outcome including controller result (GREEN 🟢 — T016, T017 pass)

**Checkpoint**: User Stories 1 AND 2 are functional — both authorization and revocation are wired to the controller

---

## Phase 5: User Story 3 — Addon Configuration for Omada Controller (Priority: P3)

**Goal**: Validate the full configuration lifecycle: addon config panel → s6 env vars → AppSettings → `app.state.omada_config` persistence across restart → per-request client/adapter creation via `get_omada_adapter` → graceful degradation when unconfigured → password masking → clean operation

**Independent Test**: Set Omada configuration options, restart the app, verify `app.state.omada_config` is populated with the correct settings and that request-scoped `OmadaClient`/`OmadaAdapter` creation uses those settings correctly; verify it also starts cleanly with no Omada config

> **NOTE**: US3's implementation IS the foundational phase (Phase 2). This phase adds integration tests that validate the end-to-end configuration lifecycle specifically, using the same per-request adapter lifecycle defined there.

### Tests for User Story 3 🔴

- [ ] T019 [P] [US3] Write integration test for end-to-end Omada config lifecycle in `tests/integration/test_omada_config_lifecycle.py` — set `CP_OMADA_*` env vars in test fixture, create app via `create_app()` and `create_guest_app()` factories, verify: (a) `app.state.omada_config` is populated from env/AppSettings with correct `base_url`, `controller_id`, `username`, `verify_ssl`, and `site_id`, (b) resolving `get_omada_adapter` (directly or through a request path that depends on it) creates an `OmadaAdapter` backed by an `OmadaClient` with those settings, (c) no network I/O occurs at startup (mock httpx to detect any connection attempts), (d) app starts and serves HTTP requests normally

- [ ] T020 [P] [US3] Write integration test for graceful degradation without Omada config in `tests/integration/test_omada_graceful_degradation.py` — start app with NO `CP_OMADA_*` env vars set, verify: (a) `app.state.omada_config` is absent or `None` and `get_omada_adapter` yields no adapter/controller wiring, (b) app starts without errors or warnings related to missing controller, (c) guest authorization flow creates grants with ACTIVE status without controller calls, (d) admin revocation flow updates DB without controller calls

- [ ] T021 [P] [US3] Write integration test for password masking in `tests/integration/test_omada_password_masking.py` — set `CP_OMADA_PASSWORD` to a known test value (e.g., `"s3cret-p@ss!"`) in test fixture, capture log output during app startup and `settings.log_effective()` at all log levels, verify the password value never appears in any log line — only `"(set)"` or `"(not set)"` is logged (FR-005)

**Checkpoint**: User Stories 1, 2, AND 3 are functional — configuration lifecycle is fully validated

---

## Phase 6: User Story 4 — Contract Tests Validate Integration Wiring (Priority: P4)

**Goal**: Unskip all existing contract tests and implement them to validate the Omada adapter/client wiring using mocks — no live controller required

**Independent Test**: Run `pytest tests/contract/tp_omada/ -v` — all previously-skipped tests execute and pass

> **NOTE**: These tests already exist as stubs with `pytest.skip()`. This phase removes skip markers and implements test bodies using `AsyncMock`/`httpx.MockTransport`.

### Implementation for User Story 4 🟢

- [ ] T022 [P] [US4] Unskip and implement authorize flow contract tests in `tests/contract/tp_omada/test_authorize_flow.py` — remove all `pytest.skip()` markers; implement each test using `AsyncMock` or `httpx.MockTransport` to mock HTTP responses; validate: (a) authorize request payload structure matches contract (`clientMac`, `site`, `time`, `authType`, `upKbps`, `downKbps`), (b) successful response parsed correctly (`grant_id`, `status`, `mac` extracted), (c) error response (HTTP 4xx) raises `OmadaClientError`, (d) authorize retries on 5xx and connection errors, (e) idempotent authorize (repeated calls safe); use real `OmadaClient` and `OmadaAdapter` classes with mocked HTTP transport (GREEN 🟢 — FR-020/021/022)

- [ ] T023 [P] [US4] Unskip and implement revoke flow contract tests in `tests/contract/tp_omada/test_revoke_flow.py` — remove all `pytest.skip()` markers; implement each test using mocked HTTP responses; validate: (a) revoke request payload structure (`clientMac`, `site`), (b) successful revoke response parsed correctly (`success`, `mac`), (c) "already revoked" (HTTP 404 or controller-specific response) treated as success (idempotent per contract), (d) error response raises `OmadaClientError`, (e) revoke retries on connection error and 5xx; use real adapter and client with mocked transport (GREEN 🟢 — FR-020/021/022)

- [ ] T024 [P] [US4] Unskip and implement error/retry contract tests in `tests/contract/tp_omada/test_adapter_error_retry.py` — remove all `pytest.skip()` markers; implement retry scenarios: (a) authorize retries on connection error with exponential backoff `[1s, 2s, 4s]`, (b) authorize retries on timeout with same backoff, (c) HTTP 4xx does NOT retry (raises `OmadaClientError` immediately), (d) HTTP 5xx retries up to 4 attempts then raises `OmadaRetryExhaustedError`, (e) revoke retries follow same pattern as authorize; mock `asyncio.sleep` to verify backoff timing without real delays; validate max total wait ≤ 7 seconds (GREEN 🟢 — FR-020/021/022)

**Checkpoint**: All contract tests pass — `pytest tests/contract/tp_omada/ -v` shows zero skipped, all green

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation port fix, REUSE compliance, linting, full test suite validation, quickstart verification

- [ ] T025 [P] Fix port 8080→8099 in guest-facing URLs in `docs/tp_omada_setup.md` — update all references where guests connect: external portal URL examples (`8080/guest/authorize` → `8099/guest/authorize`), landing page examples (`8080/success` → `8099/success`), guest-facing curl troubleshooting commands (`8080/guest/authorize` → `8099/guest/authorize`); keep admin/ingress references to 8080 where the context is administration; add 8099 port mapping in Docker examples alongside existing 8080 (FR-019)

- [ ] T026 [P] Verify REUSE compliance for all new files — ensure every new `.py` file (e.g., `dependencies.py`, new test files) has `SPDX-FileCopyrightText` and `SPDX-License-Identifier` headers; run `reuse lint` to confirm zero violations

- [ ] T027 [P] Run full linting, type-checking, and docstring coverage — execute `ruff check addon/src/ tests/`, `mypy addon/src/captive_portal/` (strict mode), and `interrogate addon/src/captive_portal/` (fail-under per project config); fix any issues in new or modified code; verify zero errors/warnings across all three tools

- [ ] T028 Run full test suite `pytest tests/ -v` — verify no regressions across unit, integration, and contract tests; all new tests pass; all previously-passing tests still pass

- [ ] T029 Run quickstart.md validation — walk through `specs/008-omada-controller-wiring/quickstart.md` verification checklist: (1) config schema, (2) settings tests, (3) s6 scripts, (4) app lifespan, (5) authorization flow, (6) revocation flow, (7) documentation port fix, (8) contract tests, (9) full suite, (10) linting, (11) types

> **Note (SC-001/SC-002)**: The 10-second authorization and revocation timing criteria require manual integration testing with a live Omada controller. These cannot be validated via automated tests.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phases 3–6)**: All depend on Foundational phase completion
  - US1 (P1) and US2 (P2) can proceed in parallel (different files: `guest_portal.py` vs `grants.py`)
  - US3 (P3) can proceed in parallel with US1/US2 (integration test files only)
  - US4 (P4) can proceed in parallel with US1/US2/US3 (contract test files only)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) — no dependencies on other stories; can run in parallel with US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) — validates foundational work via integration tests; can run in parallel with US1/US2
- **User Story 4 (P4)**: Can start after Foundational (Phase 2) — contract tests are independent of flow wiring; can run in parallel with US1/US2/US3

### Within Each User Story (TDD Cycle)

1. 🔴 **RED**: Write failing tests FIRST — confirm they fail
2. 🟢 **GREEN**: Write minimum production code to make tests pass
3. ♻️ **REFACTOR**: Clean up while keeping tests green
4. **CI tests MUST pass before manual testing** (constitution §II)

### Parallel Opportunities

- T002, T003, T004, and T005 can run in parallel (different test files)
- T008 and T009 can run in parallel (different s6 scripts)
- T013 and T014 can run in parallel (different US1 test files)
- T016 and T017 can run in parallel (different US2 test files)
- T019, T020, and T021 can run in parallel (different US3 integration test files)
- T022, T023, and T024 can run in parallel (different US4 contract test files)
- T025, T026, and T027 can run in parallel (different cross-cutting concerns)
- All user story phases (3–6) can run in parallel once Foundational is done

---

## Parallel Example: Phase 2 Foundational

```text
# RED — Launch all test tasks in parallel:
Task T002: "Write failing tests for Omada settings fields in tests/unit/config/test_settings_omada_fields.py"
Task T003: "Write failing tests for admin app lifespan Omada wiring in tests/unit/test_app_lifespan_omada.py"
Task T004: "Write failing tests for guest app lifespan Omada wiring in tests/unit/test_guest_app_lifespan_omada.py"
Task T005: "Write failing test for get_omada_adapter dependency in tests/unit/controllers/tp_omada/test_omada_dependencies.py"

# GREEN — Config + settings (sequential, T006 before T007):
Task T006: "Add Omada fields to addon/config.yaml"
Task T007: "Add Omada fields to AppSettings in settings.py"

# GREEN — s6 scripts in parallel:
Task T008: "Export CP_OMADA_* in admin s6 run script"
Task T009: "Export CP_OMADA_* in guest s6 run script"

# GREEN — Lifespan wiring (depends on T007, can run in parallel):
Task T010: "Wire Omada into admin app lifespan in app.py"
Task T011: "Wire Omada into guest app lifespan in guest_app.py"

# GREEN — DI function:
Task T012: "Create get_omada_adapter dependency in dependencies.py"
```

## Parallel Example: User Stories 1 + 2 (after Foundational)

```text
# Both user stories can start in parallel after Phase 2 completes:

# US1 — RED then GREEN:
Task T013: "Write failing tests for authorization wiring in test_guest_portal_omada.py"
Task T014: "Write failing tests for authorization errors in test_guest_portal_omada_errors.py"
Task T015: "Wire authorize into guest_portal.py"

# US2 — RED then GREEN (parallel with US1):
Task T016: "Write failing tests for revocation wiring in test_grants_omada.py"
Task T017: "Write failing tests for revocation errors in test_grants_omada_errors.py"
Task T018: "Wire revoke into grants.py"
```

## Parallel Example: User Stories 3 + 4 (can overlap with US1/US2)

```text
# US3 — Integration tests (all parallel):
Task T019: "Integration test for config lifecycle in test_omada_config_lifecycle.py"
Task T020: "Integration test for graceful degradation in test_omada_graceful_degradation.py"
Task T021: "Integration test for password masking in test_omada_password_masking.py"

# US4 — Contract tests (all parallel):
Task T022: "Implement authorize flow contract tests in test_authorize_flow.py"
Task T023: "Implement revoke flow contract tests in test_revoke_flow.py"
Task T024: "Implement error/retry contract tests in test_adapter_error_retry.py"
```

## Parallel Example: Phase 7 Polish

```text
# Launch independent tasks in parallel:
Task T025: "Fix port 8080→8099 in docs/tp_omada_setup.md"
Task T026: "Verify REUSE compliance for all new files"
Task T027: "Run linting, type-checking, and docstring coverage"

# Then sequential:
Task T028: "Run full test suite — no regressions"
Task T029: "Run quickstart.md validation"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001) — branch creation
2. Complete Phase 2: Foundational (T002–T012) — RED then GREEN
3. Complete Phase 3: User Story 1 (T013–T015) — RED then GREEN
4. **STOP and VALIDATE**: Run `pytest tests/unit/ tests/integration/ -v` — all tests GREEN
5. Deploy/demo if ready — guest authorization triggers controller call when configured

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready, settings and lifespan wired
2. Add User Story 1 → Tests GREEN → Deploy/Demo (MVP! Guest auth works with controller)
3. Add User Story 2 → Tests GREEN → Deploy/Demo (admin revocation wired)
4. Add User Story 3 → Tests GREEN → Deploy/Demo (configuration lifecycle validated)
5. Add User Story 4 → Tests GREEN → Deploy/Demo (contract tests all passing)
6. Polish → Docs fixed, compliance checked → Final quality gate
7. Each story adds value without breaking previous stories

### TDD Discipline (Constitution §II)

- 🔴 **RED**: Write the test; run it; confirm it FAILS (proves test exercises new code)
- 🟢 **GREEN**: Write the minimum production code to make it pass
- ♻️ **REFACTOR**: Clean up while keeping tests green
- **CI MUST pass** before any manual testing — manual testing without green CI is prohibited
- **Never skip the RED step** — a test that passes before implementation is not testing new behavior
- **Commit after each RED+GREEN pair** — atomic commits, one logical change per commit, DCO sign-off required

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (RED → GREEN)
2. Once Foundational is done — all 4 user stories can start in parallel:
   - Developer A: User Story 1 (guest authorization wiring in `guest_portal.py`)
   - Developer B: User Story 2 (admin revocation wiring in `grants.py`)
   - Developer C: User Story 3 (integration tests) + User Story 4 (contract tests)
3. Stories complete and integrate independently — no cross-story dependencies

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- **TDD is non-negotiable** — every production code task references which RED test it makes GREEN
- **No new controller client logic** — this feature is purely wiring; `OmadaClient` and `OmadaAdapter` are existing, stable implementations
- **Per-request construction pattern** — store only `omada_config` at startup; create `OmadaClient`/`OmadaAdapter` when handling a request/operation, with authentication occurring on first `async with client:` use
- **Per-operation context** — route handlers use `async with adapter.client:` for each authorize/revoke, not a persistent connection
- **Dual-port architecture** — admin app (8080) and guest app (8099) have independent wiring/configuration paths; neither relies on a shared startup-created client/adapter instance
- **Graceful degradation** — when Omada is not configured, all flows work exactly as before (DB-only grants)
- **Password security** — `omada_password` is NEVER logged; `log_effective()` shows only `"(set)"` or `"(not set)"`
- All commits require DCO sign-off (`git commit -s`) and SPDX headers on new files
- Stop at any checkpoint to validate story independently
