SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Omada OpenAPI Migration

**Input**: Design documents from `/specs/013-omada-openapi-migration/`
**Prerequisites**: spec.md (user stories P1-P3), plan.md, research.md,
data-model.md, quickstart.md, contracts/controller-adapter.md,
contracts/openapi-contracts.md

**Tests**: TDD is MANDATORY per project constitution §II. Every unit of
production code is preceded by a failing test (Red-Green-Refactor). Unit and
contract tests precede implementation; integration tests are included in the
phase where their prerequisites exist.

**Organization**: Tasks are grouped by independently testable phases that map to
user stories and settled plan increments.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task supports (US1, US2, US3)
- 🔴 = RED (failing test written first) · 🟢 = GREEN (production code makes test pass)
- Include exact file paths in descriptions

## Path Conventions

- **Addon source**: `addon/src/captive_portal/`
- **Controllers**: `addon/src/captive_portal/controllers/tp_omada/`
- **Config**: `addon/src/captive_portal/config/`
- **Models**: `addon/src/captive_portal/models/`
- **Persistence**: `addon/src/captive_portal/persistence/`
- **Services**: `addon/src/captive_portal/services/`
- **Admin routes/UI**: `addon/src/captive_portal/api/routes/`,
  `addon/src/captive_portal/web/templates/admin/`,
  `addon/src/captive_portal/web/themes/default/`
- **Addon config/services**: `addon/config.yaml`,
  `addon/rootfs/etc/s6-overlay/s6-rc.d/`
- **Tests (unit)**: `tests/unit/`
- **Tests (integration)**: `tests/integration/`
- **Tests (contract)**: `tests/contract/tp_omada/`
- **Documentation**: `addon/README.md`, `docs/`,
  `specs/013-omada-openapi-migration/quickstart.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Start the implementation from the merged spec/plan/tasks baseline.

- [ ] T001 Create implementation branch `013-omada-openapi-migration` from
  `main`, confirm `specs/013-omada-openapi-migration/` contains the merged
  spec, plan, research, data model, quickstart, contracts, and this tasks file

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared Protocol and configuration storage that all
backend work depends on.

**⚠️ CRITICAL**: No backend implementation work can begin until this phase is
complete.

### Tests for Foundational (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T002 [P] [US1] Write failing Protocol conformance tests in
  `tests/unit/controllers/tp_omada/test_adapter_protocol.py` verifying that
  `OmadaControllerAdapter` exposes async `authorize`, `revoke`, `update`, and
  `get_status` signatures from `contracts/controller-adapter.md`, accepts
  legacy gateway/EAP parameters, and is satisfied by fake legacy and OpenAPI
  adapters (RED 🔴)

- [ ] T003 [P] [US3] Write failing model tests in
  `tests/unit/models/test_omada_config_model.py` for `OmadaConfig.client_id`,
  `OmadaConfig.encrypted_client_secret`, `OmadaConfig.openapi_mode` defaulting
  to `"auto"`, legacy/openapi credential completeness predicates, partial
  OpenAPI credential detection, and rejection of invalid `openapi_mode` values
  (RED 🔴)

- [ ] T004 [P] [US3] Write failing migration tests in
  `tests/unit/persistence/test_migrate_omada_openapi_fields.py` and
  `tests/unit/services/test_config_migration.py` verifying `init_db()` adds
  `client_id`, `encrypted_client_secret`, and `openapi_mode` to existing
  `omada_config` SQLite rows with `openapi_mode='auto'`;
  `migrate_yaml_to_db()` persists `omada_client_id`, encrypts
  `omada_client_secret`, stores `omada_openapi_mode`, preserves existing
  ciphertext when the secret is unchanged, and requires no operator action for
  legacy-only upgrades (RED 🔴)

- [ ] T005 [P] [US3] Write failing credential tests in
  `tests/unit/security/test_credential_encryption.py` verifying
  `client_secret` encryption/decryption uses the existing Fernet helpers,
  rejects empty plaintext/ciphertext, and never logs plaintext secrets (RED 🔴)

- [ ] T006 [P] [US3] Write failing three-tier migration settings tests in
  `tests/unit/config/test_settings_omada_openapi_fields.py` verifying
  `_load_for_migration()` resolves `omada_client_id`, `omada_client_secret`,
  and `omada_openapi_mode` by addon option → `CP_OMADA_*` environment variable
  → default, trims strings, validates `auto|openapi|legacy`, and redacts the
  secret from `log_effective()` output (RED 🔴)

### Implementation for Foundational (GREEN) 🟢

- [ ] T007 [US1] Create
  `addon/src/captive_portal/controllers/tp_omada/adapter_protocol.py` with the
  `OmadaControllerAdapter` Protocol from `contracts/controller-adapter.md`, full
  type annotations, docstrings, and SPDX header (GREEN 🟢 — T002 passes)

- [ ] T008 [US3] Extend
  `addon/src/captive_portal/models/omada_config.py` with `client_id`,
  `encrypted_client_secret`, `openapi_mode`, legacy/openapi completeness
  properties, partial OpenAPI credential helpers, and assignment validation for
  supported modes `auto`, `openapi`, and `legacy` (GREEN 🟢 — T003 passes)

- [ ] T009 [US3] Add `_migrate_omada_openapi_fields()` to
  `addon/src/captive_portal/persistence/database.py` and call it from
  `init_db()` so existing databases gain `client_id`,
  `encrypted_client_secret`, and `openapi_mode` without losing legacy settings
  (GREEN 🟢 — T004 passes)

- [ ] T010 [US3] Extend OpenAPI credential handling in
  `addon/src/captive_portal/services/config_migration.py` to encrypt
  `omada_client_secret`, preserve existing `encrypted_client_secret` when the
  DB already has a value, and keep legacy-only upgrades on the legacy backend
  (GREEN 🟢 — T004 and T005 pass)

- [ ] T011 [US3] Extend migration-only maps, defaults, validators, coercion, and
  secret-safe logging in `addon/src/captive_portal/config/settings.py` for
  `omada_client_id`, `omada_client_secret`, and `omada_openapi_mode`; extend
  `addon/config.yaml` schema with optional `omada_client_id`,
  `omada_client_secret`, and `omada_openapi_mode` entries (GREEN 🟢 — T006
  passes)

- [ ] T012 [US3] Verify s6 service scripts
  `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal/run` and
  `addon/rootfs/etc/s6-overlay/s6-rc.d/captive-portal-guest/run` continue to
  treat Omada settings as DB/UI-managed and do not export
  `CP_OMADA_CLIENT_SECRET`; ensure three-tier migration reads addon
  `options.json` directly and only honors `CP_OMADA_CLIENT_ID`,
  `CP_OMADA_CLIENT_SECRET`, and `CP_OMADA_OPENAPI_MODE` when operators provide
  environment variables externally (GREEN 🟢 — supports T006 without leaking
  secrets through s6 logs)

**Checkpoint**: Protocol and persistent configuration are ready; all Phase 2
unit tests pass.

---

## Phase 3: User Story 1 — OpenAPI Happy-Path Adapter (Priority: P1) 🎯 MVP

**Goal**: An OpenAPI-capable controller can authorize, unauthorize, and report
status for guests through the documented OpenAPI backend while preserving
existing guest/admin outcomes.

**Independent Test**: Run OpenAPI client/adapter unit and contract tests with
mocked `httpx` responses and verify token, site, MAC, auth, unauth, and status
mapping without a live controller.

### Tests for User Story 1 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T013 [P] [US1] Write failing token tests in
  `tests/unit/controllers/tp_omada/test_openapi_client_token.py` for
  `client_credentials` token acquisition, `refresh_token` renewal with a
  300-second margin, `Authorization: AccessToken=<token>` header generation,
  SSL verification propagation, bounded timeouts, and secret/token redaction in
  exceptions and logs (RED 🔴)

- [ ] T014 [P] [US1] Write failing controller ID and site cache tests in
  `tests/unit/controllers/tp_omada/test_openapi_site_cache.py` for `/api/info`
  discovery when `controller_id` is empty, paginated
  `GET /openapi/v1/{omadacId}/sites`, matching `name == site_name`, accepting
  `siteId` or `id`, caching the selected site ID for the add-on run, and using
  `asyncio.Lock` for single-flight discovery (RED 🔴)

- [ ] T015 [P] [US1] Write failing MAC formatting tests in
  `tests/unit/controllers/tp_omada/test_openapi_mac_formatting.py` for
  colon-separated, lowercase, uppercase, and dash-separated valid MACs mapping
  to `AA-BB-CC-DD-EE-FF`, and invalid MACs raising `OmadaClientError` before an
  HTTP call (RED 🔴)

- [ ] T016 [P] [US1] Write failing authorize contract tests in
  `tests/contract/tp_omada/test_openapi_authorize_flow.py` verifying
  `POST /openapi/v1/{omadacId}/sites/{siteId}/hotspot/clients/{mac}/auth` sends
  no required duration body, returns `{"grant_id": mac, "status": "active"}`,
  ignores legacy gateway/EAP parameters, retries 429/5xx, and maps
  `errorCode != 0` to an Omada-compatible error without secrets (RED 🔴)

- [ ] T017 [P] [US1] Write failing unauth/status contract tests in
  `tests/contract/tp_omada/test_openapi_revoke_status_flow.py` verifying
  `POST .../unauth` for admin revoke, early revoke, and expiry
  deauthorization; idempotent already-unauthorized responses; paginated
  `GET .../hotspot/authed-records` status mapping to `authorized` and
  `remaining_seconds` best-effort fields; and `update()` semantics that do not
  introduce undocumented duration body fields (RED 🔴)

### Implementation for User Story 1 (GREEN) 🟢

- [ ] T018 [US1] Create
  `addon/src/captive_portal/controllers/tp_omada/openapi_client.py` implementing
  OpenAPI token acquisition, proactive refresh, `AccessToken=` headers,
  controller ID discovery, shared token state guarded by `asyncio.Lock`, retry
  behavior compatible with `OmadaClientError`/`OmadaRetryExhaustedError`, and
  secret-safe logging (GREEN 🟢 — T013 passes)

- [ ] T019 [US1] Create
  `addon/src/captive_portal/controllers/tp_omada/openapi_adapter.py` implementing
  `OmadaControllerAdapter` with site discovery/cache, MAC normalization, timer-
  only `authorize`, `unauth`-based `revoke`, `update` without undocumented
  duration fields, and authed-records `get_status` mapping (GREEN 🟢 — T014,
  T015, T016, T017 pass)

- [ ] T020 [US1] Update `tests/contract/tp_omada/test_authorize_flow.py`,
  `tests/contract/tp_omada/test_revoke_flow.py`, and
  `tests/contract/tp_omada/test_adapter_error_retry.py` only as needed to keep
  existing legacy contract coverage green while adding OpenAPI contract coverage
  under separate test files (GREEN 🟢)

**Checkpoint**: The OpenAPI backend is independently functional and contract-
tested with mocked controller responses.

---

## Phase 4: User Story 2 — Legacy Fallback and Startup Selection (Priority: P2)

**Goal**: Existing legacy deployments continue working without configuration
changes, and automatic backend selection chooses OpenAPI only when credentials
and the startup capability probe succeed.

**Independent Test**: Run legacy extraction, factory, dependency, lifecycle, and
fallback integration tests with mocked probe outcomes; verify selected backend
stays fixed for the app run.

### Tests for User Story 2 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T021 [P] [US2] Write failing legacy extraction tests in
  `tests/unit/controllers/tp_omada/test_legacy_adapter_extraction.py` verifying
  current `OmadaAdapter`/`OmadaClient` behavior is preserved by
  `OmadaLegacyAdapter` and `OmadaLegacyClient`, including legacy auth payloads,
  Gateway/EAP parameters, retry behavior, status mapping, and compatibility
  imports from `adapter.py` and `base_client.py` (RED 🔴)

- [ ] T022 [P] [US2] Write failing factory selection tests in
  `tests/unit/controllers/tp_omada/test_adapter_factory_selection.py` covering
  the plan table for `auto` mode: complete OpenAPI credentials + successful
  token probe selects OpenAPI; absent/partial OpenAPI credentials with complete
  legacy selects legacy and logs a missing-field warning; failed probe with
  complete legacy selects legacy and logs an actionable warning; no usable
  backend raises a clear configuration error (RED 🔴)

- [ ] T023 [P] [US2] Write failing dependency tests in
  `tests/unit/controllers/tp_omada/test_omada_dependencies.py` verifying
  `get_omada_adapter()` reads selected runtime backend from `request.app.state`,
  returns a fresh `OmadaLegacyAdapter` or `OmadaOpenApiAdapter` per request,
  shares only explicit OpenAPI token/site cache state, and returns `None` when
  no backend is configured (RED 🔴)

- [ ] T024 [P] [US2] Write failing admin/guest lifespan tests in
  `tests/unit/test_app_lifespan_omada.py` and
  `tests/unit/test_guest_app_lifespan_omada.py` verifying startup calls the
  selection factory once, stores immutable backend selection/runtime config on
  `app.state`, logs selected backend and secret-safe reason, and avoids
  constructing shared legacy client instances (RED 🔴)

- [ ] T025 [P] [US2] Write failing integration tests in
  `tests/integration/test_omada_legacy_fallback.py` verifying an upgraded
  legacy-only configuration selects legacy automatically, guest authorization,
  admin revocation, status, and existing contract tests preserve pre-migration
  behavior, and OpenAPI credential absence requires no operator action (RED 🔴)

- [ ] T026 [P] [US1] Write failing grant-expiry timer tests in
  `tests/unit/services/test_grant_expiry_service.py` and lifespan wiring tests
  in `tests/unit/test_app_lifespan_omada.py` verifying ACTIVE grants whose
  `end_utc` has passed are processed by a scheduled expiry worker, call the
  selected adapter's `revoke`/OpenAPI `unauth` within the existing 5-second
  processing target, mark grants `EXPIRED`, log/audit controller failures, do
  not retry by switching backends, and start/stop the worker cleanly with the
  app lifecycle (RED 🔴)

### Implementation for User Story 2 (GREEN) 🟢

- [ ] T027 [US2] Extract current legacy behavior into
  `addon/src/captive_portal/controllers/tp_omada/legacy_client.py` and
  `addon/src/captive_portal/controllers/tp_omada/legacy_adapter.py`; leave
  `adapter.py` and `base_client.py` as compatibility imports or wrappers so
  existing imports and tests continue to pass (GREEN 🟢 — T021 passes)

- [ ] T028 [US2] Create
  `addon/src/captive_portal/controllers/tp_omada/adapter_factory.py` with the
  startup capability probe and backend selection rules from `plan.md`, using an
  OpenAPI token probe for capability detection and secret-safe warnings/errors
  for fallback or no-usable-backend outcomes (GREEN 🟢 — T022 passes)

- [ ] T029 [US2] Update
  `addon/src/captive_portal/controllers/tp_omada/dependencies.py` to return the
  selected `OmadaControllerAdapter` implementation from `app.state` runtime
  config, creating fresh request-scoped legacy clients and guarded OpenAPI
  adapters/caches as required by `contracts/controller-adapter.md`; preserve the
  existing per-request Omada `site` query override for legacy requests without
  route handlers mutating backend-specific adapter attributes (GREEN 🟢 — T023
  passes)

- [ ] T030 [US2] Update `addon/src/captive_portal/app.py` and
  `addon/src/captive_portal/guest_app.py` to load `OmadaConfig`, call the
  adapter factory at startup, store selected backend runtime config on
  `app.state`, and log `Omada backend selected: openapi|legacy` with no
  secrets or tokens (GREEN 🟢 — T024 passes)

- [ ] T031 [US2] Update `addon/src/captive_portal/api/routes/guest_portal.py`,
  `addon/src/captive_portal/api/routes/grants.py`, and
  `addon/src/captive_portal/api/routes/grants_ui.py` type hints/imports to
  depend on `OmadaControllerAdapter` instead of concrete `OmadaAdapter`;
  move the `async with adapter.client` session lifecycle out of route
  handlers and into the adapter methods per
  `contracts/controller-adapter.md` (the Protocol exposes no `.client`)
  so routes call `adapter.authorize`/`adapter.revoke` directly; remove
  direct `site_id` mutation from guest route code by using the
  Protocol-safe per-request site override from T029; preserve guest
  success/error redirects, admin API partial-failure semantics, and
  admin UI revoke behavior (GREEN 🟢 — T025 supports flow parity)

- [ ] T032 [US1] Create or extend
  `addon/src/captive_portal/services/grant_expiry_service.py` to run a bounded
  periodic expiry worker that selects due ACTIVE grants, calls the selected
  adapter's `revoke`/OpenAPI `unauth`, marks grants `EXPIRED`, records
  audit/error details, and never sends undocumented OpenAPI duration fields;
  wire startup/shutdown in `addon/src/captive_portal/app.py` so expiry
  deauthorization is timer-driven rather than only lazy route recomputation
  (GREEN 🟢 — T026 passes)

**Checkpoint**: Automatic selection, legacy fallback, app-state wiring, and
expiry deauthorization are functional with existing deployments preserved.

---

## Phase 5: User Story 3 — Backend Selection Control and Operator Config (Priority: P3)

**Goal**: Operators can set `openapi_mode` to `auto`, `openapi`, or `legacy`,
manage OpenAPI credentials safely, and receive clear validation/errors without
changing guest or admin workflows.

**Independent Test**: Change only `openapi_mode` and credential presence in
unit/integration tests, restart or save settings, and verify selected backend or
startup/configuration failure for every supported mode.

### Tests for User Story 3 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T033 [P] [US3] Write failing forced-mode factory tests in
  `tests/unit/controllers/tp_omada/test_adapter_factory_modes.py` verifying
  `openapi_mode='legacy'` skips OpenAPI probe even with credentials,
  `openapi_mode='openapi'` requires complete OpenAPI credentials and a
  successful probe, forced OpenAPI never falls back to legacy, and invalid mode
  values produce actionable supported-value messages (RED 🔴)

- [ ] T034 [P] [US3] Write failing Omada settings route tests in
  `tests/unit/routes/test_omada_settings_openapi.py` verifying
  `update_omada_settings()` accepts `client_id`, `client_secret`,
  `client_secret_changed`, and `openapi_mode`; encrypts the client secret;
  preserves existing ciphertext when unchanged; validates supported modes; and
  excludes secrets from audit metadata, redirects, and log messages (RED 🔴)

- [ ] T035 [P] [US3] Write failing Omada settings UI integration tests in
  `tests/integration/test_omada_settings_ui.py` for rendering the OpenAPI
  Client ID, Client Secret, and Backend Mode controls in
  `addon/src/captive_portal/web/templates/admin/omada_settings.html`, showing
  masked secret state, showing whether backend changes require an add-on
  restart for the separate guest listener, and submitting values through
  `admin-omada-settings.js` without exposing secret values (RED 🔴)

- [ ] T036 [P] [US3] Write failing end-to-end backend selection tests in
  `tests/integration/test_omada_openapi_backend_selection.py` and
  `tests/integration/test_omada_forced_modes.py` covering automatic OpenAPI
  selection, automatic fallback warning, forced legacy selection, forced OpenAPI
  missing-credential failure, failed-probe failure, selected backend staying
  fixed after mid-session token refresh failure, and the documented behavior for
  guest-listener backend refresh after admin settings changes (RED 🔴)

- [ ] T037 [P] [US3] Extend failing secret-safety tests in
  `tests/integration/test_omada_password_masking.py` verifying legacy passwords,
  OpenAPI client secrets, access tokens, and refresh tokens appear in zero
  startup logs, probe logs, validation messages, audit records, and admin UI
  responses (RED 🔴)

### Implementation for User Story 3 (GREEN) 🟢

- [ ] T038 [US3] Extend
  `addon/src/captive_portal/controllers/tp_omada/adapter_factory.py` for forced
  `legacy` and forced `openapi` behavior, invalid-mode validation, clear
  no-fallback errors, partial-credential warnings, and fixed-backend semantics
  after token/site/operation failures (GREEN 🟢 — T033 passes)

- [ ] T039 [US3] Update
  `addon/src/captive_portal/api/routes/omada_settings_ui.py` to load, validate,
  save, and audit `client_id`, encrypted `client_secret`, and `openapi_mode`;
  rebuild selected backend runtime config on save for the admin process; clearly
  report whether the separate guest listener needs an add-on restart to adopt
  backend changes; and report connection/probe failures with actionable,
  secret-safe messages (GREEN 🟢 — T034 passes)

- [ ] T040 [US3] Update
  `addon/src/captive_portal/web/templates/admin/omada_settings.html` and
  `addon/src/captive_portal/web/themes/default/admin-omada-settings.js` with
  OpenAPI credential fields, a backend mode selector (`auto`, `openapi`,
  `legacy`), client-side mode validation, guest-listener restart guidance when
  backend settings change, and masked secret-change handling matching the
  existing password pattern (GREEN 🟢 — T035 passes)

- [ ] T041 [US3] Update `addon/src/captive_portal/config/omada_config.py` so
  `build_omada_config()` decrypts both legacy password and OpenAPI client
  secret as needed, builds backend-aware runtime selection input, validates mode
  and controller ID consistently, and never requires legacy username/password in
  forced OpenAPI mode (GREEN 🟢 — T036 passes)

- [ ] T042 [US3] Add OpenAPI mode and credential behavior to admin and audit
  integration coverage in `tests/integration/test_omada_config_lifecycle.py`,
  `tests/integration/test_omada_graceful_degradation.py`, and
  `tests/integration/test_omada_password_masking.py` so existing configuration
  lifecycle tests cover both backends (GREEN 🟢 — T036, T037 pass)

**Checkpoint**: Operators can manage OpenAPI credentials and backend mode safely;
all three user stories are independently testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, compliance, quality gates, and task-list maintenance
conventions.

- [ ] T043 [P] Update operator documentation in `addon/README.md`,
  `docs/addon/config.md`, `docs/addon/configuration.md`, and
  `docs/tp_omada_setup.md` to explain OpenAPI app setup, `client_id`,
  `client_secret`, `openapi_mode`, automatic legacy fallback, forced modes,
  selected-backend logs, SSL behavior, any add-on restart requirement for the
  separate guest listener, and timer-only duration guidance for the Omada
  hotspot portal profile

- [ ] T044 [P] Update `specs/013-omada-openapi-migration/quickstart.md` if
  implementation details changed during TDD, preserving the settled timer-only
  duration policy and developer verification commands using `uv`

- [ ] T045 [P] Verify REUSE compliance for all new files under
  `addon/src/captive_portal/controllers/tp_omada/`, `tests/unit/`,
  `tests/contract/tp_omada/`, and `tests/integration/`; ensure SPDX headers are
  present and run `uv run reuse lint`

- [ ] T046 [P] Run targeted tests for the OpenAPI migration:

  ```bash
  uv run pytest \
    tests/unit/config/ \
    tests/unit/models/test_omada_config_model.py \
    tests/unit/persistence/test_migrate_omada_openapi_fields.py \
    tests/unit/security/test_credential_encryption.py \
    tests/unit/services/test_config_migration.py \
    tests/unit/services/test_grant_expiry_service.py \
    tests/unit/controllers/tp_omada/ \
    tests/unit/routes/test_omada_settings_openapi.py \
    tests/unit/test_app_lifespan_omada.py \
    tests/unit/test_guest_app_lifespan_omada.py \
    tests/contract/tp_omada/ \
    tests/integration/test_omada_config_lifecycle.py \
    tests/integration/test_omada_graceful_degradation.py \
    tests/integration/test_omada_legacy_fallback.py \
    tests/integration/test_omada_openapi_backend_selection.py \
    tests/integration/test_omada_forced_modes.py \
    tests/integration/test_omada_settings_ui.py \
    -v
  ```

- [ ] T047 [P] Run code quality gates: `uv run ruff check addon/src/ tests/`,
  `uv run mypy addon/src/captive_portal`,
  `uv run interrogate addon/src/captive_portal/`, and
  `uv run pre-commit run --all-files`; fix all issues including docstring
  coverage, C901 complexity regressions, YAML lint, shell/script lint, and docs
  compliance

- [ ] T048 Run full regression suite `uv run pytest tests/ -v` and confirm no
  legacy behavior regressions, no skipped Omada contract tests, and CI-equivalent
  success before opening the implementation PR

- [ ] T049 Run quickstart and performance validation from
  `specs/013-omada-openapi-migration/quickstart.md`, including backend-mode
  scenarios, duration guidance, and SC-006/SC-007 timing checks; run existing
  performance tests such as `uv run pytest tests/performance/test_redeem_latency.py -v`
  with controller calls mocked, and document any live-controller-only propagation
  checks in the implementation PR body rather than marking automated tests
  complete

- [ ] T050 In the implementation PR only, mark completed checkboxes in this
  `specs/013-omada-openapi-migration/tasks.md` file as a separate documentation
  commit after the functional code commits; do not combine code changes with
  task-completion checkbox updates

> **Note (SC-006/SC-007)**: Controller propagation within 25 seconds and
> expiry/revoke deauthorization initiation within 5 seconds require integration
> validation against a live Omada controller or representative test harness.
> Automated tests must mock timing boundaries, but live validation may be manual
> after CI is green.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all backend
  implementation
- **OpenAPI Happy Path (Phase 3 / US1)**: Depends on Foundational completion
- **Legacy Fallback + Factory (Phase 4 / US2)**: Depends on Foundational and
  uses the OpenAPI adapter from Phase 3 for successful-probe paths
- **Selection Control + Operator Config (Phase 5 / US3)**: Depends on Phase 4
  factory/lifecycle wiring and extends mode-specific behavior
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational; delivers the OpenAPI backend
  independently with mocked controller contracts
- **User Story 2 (P2)**: Starts after Foundational and Phase 3 adapter basics;
  preserves legacy behavior and wires selected backend startup/fallback
- **User Story 3 (P3)**: Starts after factory/lifecycle wiring; adds operator
  mode control, UI/config migration, forced-mode validation, and docs

### Within Each User Story (TDD Cycle)

1. 🔴 **RED**: Write failing tests FIRST — confirm they fail
2. 🟢 **GREEN**: Write minimum production code to make tests pass
3. ♻️ **REFACTOR**: Clean up while keeping tests green
4. **CI tests MUST pass before manual testing** (constitution §II)

### Parallel Opportunities

- T002-T006 can run in parallel (different foundational test files)
- T007-T012 can run partly in parallel after their matching tests exist, except
  shared model/migration changes must be coordinated
- T013-T017 can run in parallel (different OpenAPI test/contract files)
- T018 and T019 are sequential for client → adapter, while T020 can run after
  legacy contracts are known
- T021-T026 can run in parallel (legacy, factory, dependency, lifecycle,
  integration, and expiry test files)
- T027-T032 are mostly sequential because factory/dependency/lifecycle wiring
  builds on legacy extraction
- T033-T037 can run in parallel (different mode/UI/secret tests)
- T038-T042 are sequential where factory/config/UI changes touch shared files
- T043-T047 can run in parallel after implementation is complete; T048-T050 are
  final sequential validation and documentation maintenance

---

## Parallel Example: Phase 3 OpenAPI Backend

```text
# RED — Launch independent OpenAPI tests in parallel:
Task T013: "Write token tests in test_openapi_client_token.py"
Task T014: "Write site cache tests in test_openapi_site_cache.py"
Task T015: "Write MAC formatting tests in test_openapi_mac_formatting.py"
Task T016: "Write OpenAPI authorize contract tests"
Task T017: "Write OpenAPI unauth/status contract tests"

# GREEN — Implement client before adapter:
Task T018: "Create openapi_client.py"
Task T019: "Create openapi_adapter.py"
Task T020: "Keep legacy contract coverage green"
```

## Parallel Example: Phase 4 Fallback Wiring

```text
# RED — Launch tests in parallel:
Task T021: "Legacy extraction tests"
Task T022: "Factory auto-selection tests"
Task T023: "Dependency selected-backend tests"
Task T024: "Admin/guest lifespan tests"
Task T025: "Legacy fallback integration tests"
Task T026: "Expiry deauthorization tests"

# GREEN — Sequential integration path:
Task T027: "Extract legacy client/adapter"
Task T028: "Create adapter factory"
Task T029: "Update get_omada_adapter"
Task T030: "Wire app and guest_app lifespan"
Task T031: "Retype routes to Protocol"
Task T032: "Wire expiry revoke"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002-T012) — RED then GREEN
3. Complete Phase 3: OpenAPI happy-path backend (T013-T020) — RED then GREEN
4. **STOP and VALIDATE**: Run targeted OpenAPI unit/contract tests; all green

### Incremental Delivery

1. Foundational Protocol/config → tests green
2. OpenAPI adapter → token/site/auth/unauth/status contracts green
3. Legacy extraction + factory → existing deployments and auto fallback green
4. Forced mode + operator config → UI/config and mode tests green
5. Polish → docs, REUSE, ruff, mypy, interrogate, full test suite green

### TDD Discipline (Constitution §II)

- 🔴 **RED**: Write the test; run it; confirm it FAILS
- 🟢 **GREEN**: Write the minimum production code to make it pass
- ♻️ **REFACTOR**: Improve design while keeping tests green
- **Never skip RED** — tests that pass before implementation do not prove new
  behavior
- Keep commits atomic; task-list checkbox updates are a separate docs commit in
  the implementation PR

---

## Notes

- [P] tasks = different files, no dependency on incomplete tasks
- [Story] labels map to spec user stories for traceability
- The selected backend is fixed for the app run; no mid-operation fallback from
  OpenAPI to legacy is allowed
- Duration handling is timer-only; OpenAPI `authorize` must not depend on
  undocumented per-call duration fields
- Existing legacy deployments must continue working without OpenAPI credentials
  or operator action
- Secrets and tokens must never appear in logs, audit records, validation
  messages, redirects, or admin UI responses
- All new source and test files require SPDX headers
- Use `uv` for tests and quality gates; do not add new tooling unless a required
  existing command fails because dependencies are missing
