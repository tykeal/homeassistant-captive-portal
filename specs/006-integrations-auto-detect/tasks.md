SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Integrations Auto-Detection

**Input**: Design documents from `/specs/006-integrations-auto-detect/`
**Prerequisites**: spec.md (user stories with priorities P1–P4)

**Tests**: TDD is MANDATORY per project constitution §II. Every unit of production code is preceded by a failing test (Red-Green-Refactor). Unit tests precede implementation; integration, acceptance, performance, and edge-case tests are included in appropriate phases.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- 🔴 = RED (failing test written first) · 🟢 = GREEN (production code makes test pass)
- Include exact file paths in descriptions

## Path Conventions

- **Addon source**: `addon/src/captive_portal/`
- **Templates**: `addon/src/captive_portal/web/templates/admin/`
- **Static assets**: `addon/src/captive_portal/web/themes/default/`
- **Integrations layer**: `addon/src/captive_portal/integrations/`
- **API routes**: `addon/src/captive_portal/api/routes/`
- **Tests (unit)**: `tests/unit/`
- **Tests (integration)**: `tests/integration/`
- **Tests (performance)**: `tests/performance/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch creation, discovery data model, and HA API access foundations

- [ ] T001 Create feature branch `006-integrations-auto-detect` from `main`

### Tests for Setup (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T002 [P] Write failing unit tests for HA settings fields in `tests/unit/config/test_settings_ha_fields.py` — verify `AppSettings` exposes `ha_base_url` defaulting to `http://supervisor/core/api` and `ha_token` read from `SUPERVISOR_TOKEN` env var; test env-var fallbacks `CP_HA_BASE_URL` and `CP_HA_TOKEN`; test that missing token raises or defaults safely (RED 🔴)
- [ ] T003 [P] Write failing unit tests for `DiscoveredIntegration` and `DiscoveryResult` models in `tests/unit/integrations/test_discovered_integration_model.py` — validate field types, defaults (`already_configured=False`, `state_display` derived from `state`, nullable `event_summary`/`event_start`/`event_end`), JSON serialization round-trip, required fields (`entity_id`, `friendly_name`) raise `ValidationError` when missing; also test `DiscoveryResult` wrapper: `available=True` with integrations list, `available=False` with `error_message` and `error_category`, empty integrations list when unavailable (RED 🔴)

### Implementation for Setup (GREEN) 🟢

- [ ] T004 [P] Add `ha_base_url: str` and `ha_token: str` fields to `AppSettings` in `addon/src/captive_portal/config/settings.py` — read `SUPERVISOR_TOKEN` from environment, default `ha_base_url` to `http://supervisor/core/api`; add env-var fallbacks `CP_HA_BASE_URL` and `CP_HA_TOKEN`; update `_ADDON_OPTION_MAP` and `_ENV_VAR_MAP` so these fields participate in the existing three-tier resolution; extend the `AppSettings.load()` resolution loop to include these fields with appropriate validation/coercion, following the same pattern used when `guest_external_url` was added in specs/004 (GREEN 🟢 — T002 passes)
- [ ] T005 [P] Create `DiscoveredIntegration` and `DiscoveryResult` Pydantic models in `addon/src/captive_portal/integrations/ha_discovery_service.py` — transient (not persisted); `DiscoveredIntegration` fields: `entity_id: str`, `friendly_name: str`, `state: str` (raw HA state: "on"/"off"/"unavailable"), `state_display: str` (derived: "Active booking"/"No active bookings"/"Unavailable"), `event_summary: str | None = None` (from `attributes.message`), `event_start: str | None = None` (from `attributes.start_time`), `event_end: str | None = None` (from `attributes.end_time`), `already_configured: bool = False`; `DiscoveryResult` wrapper fields: `available: bool`, `integrations: list[DiscoveredIntegration] = Field(default_factory=list)`, `error_message: str | None = None`, `error_category: str | None = None` (one of "timeout", "auth", "connection", "server_error", "unknown") (GREEN 🟢 — T003 passes)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: HA entity discovery service that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T006 [P] Write failing unit tests for `HADiscoveryError` exception hierarchy in `tests/unit/integrations/test_ha_discovery_errors.py` — verify base `HADiscoveryError` carries `user_message` (safe, no secrets) and `detail` (full diagnostic); verify subclasses `HAConnectionError`, `HAAuthenticationError` (401), `HATimeoutError`, `HAServerError` (5xx) each inherit correctly; verify `str()` returns only safe `user_message` (RED 🔴)
- [ ] T007 [P] Write failing unit tests for `get_all_states` in `tests/unit/integrations/test_ha_client_discovery.py` — mock httpx responses: (a) success returns full entity list (no filtering), (b) HTTP 401 → `HAAuthenticationError`, (c) HTTP 500 → `HAServerError`, (d) `httpx.ConnectError` → `HAConnectionError`, (e) `httpx.TimeoutException` → `HATimeoutError`; verify 10s configurable timeout is passed to the HTTP call (RED 🔴)
- [ ] T008 [P] Write failing unit tests for `HADiscoveryService.discover()` in `tests/unit/integrations/test_ha_discovery_service.py` — mock `HAClient` and DB session: (a) verify filters `get_all_states()` results for `calendar.rental_control_*` entities and maps to `DiscoveredIntegration` models, (b) sets `already_configured=True` for entities matching existing `HAIntegrationConfig.integration_id` rows, (c) extracts `state`, `state_display`, `event_summary`, `event_start`, `event_end` from entity attributes, (d) returns `DiscoveryResult` wrapper, (e) re-raises `HADiscoveryError` subtypes from `ha_client` as `DiscoveryResult` with `available=False` (RED 🔴)
- [ ] T012 Write failing unit test for `get_ha_client` FastAPI dependency in `tests/unit/integrations/test_ha_client_dependency.py` — verify `HAClient` is instantiated from `AppSettings.ha_base_url` and `AppSettings.ha_token` during app lifespan startup, stored on `app.state`, and `get_ha_client()` dependency returns the instance; verify client is closed on shutdown (RED 🔴)

### Implementation for Foundational (GREEN) 🟢

- [ ] T009 [P] Create `HADiscoveryError` exception hierarchy in `addon/src/captive_portal/integrations/ha_errors.py` — base `HADiscoveryError(user_message, detail)`, subclasses `HAConnectionError`, `HAAuthenticationError`, `HATimeoutError`, `HAServerError`; each carries safe user-facing message (no tokens or internal URLs) and full detail for server-side logging; `__str__` returns `user_message` only (GREEN 🟢 — T006 passes)
- [ ] T010 [P] Add `get_all_states` method to `addon/src/captive_portal/integrations/ha_client.py` — call `GET /states` on HA REST API (the `HAClient.base_url` already includes the `/api` segment), return `list[dict[str, Any]]` of all entity state dicts (thin HTTP wrapper, no filtering); handle `httpx.ConnectError` → `HAConnectionError`, HTTP 401 → `HAAuthenticationError`, HTTP 5xx → `HAServerError`, `httpx.TimeoutException` → `HATimeoutError`; use configurable timeout (default 10s) (GREEN 🟢 — T007 passes)
- [ ] T011 Create `HADiscoveryService` in `addon/src/captive_portal/integrations/ha_discovery_service.py` — accepts `HAClient` and DB `Session`; method `discover() -> DiscoveryResult` calls `ha_client.get_all_states()`, filters for entities whose `entity_id` starts with `calendar.rental_control_`, maps to `DiscoveredIntegration` models (extracting `state`, `state_display`, `event_summary` from `attributes.message`, `event_start` from `attributes.start_time`, `event_end` from `attributes.end_time`), cross-references existing `HAIntegrationConfig` rows to set `already_configured` flag; on `HADiscoveryError` returns `DiscoveryResult(available=False, error_message=..., error_category=...)` and logs full error details server-side (GREEN 🟢 — T008 passes)
- [ ] T013 Register `HAClient` as FastAPI dependency in `addon/src/captive_portal/app.py` — instantiate `HAClient(settings.ha_base_url, settings.ha_token)` during lifespan startup, store on `app.state`, close on shutdown; create `get_ha_client` dependency function in `addon/src/captive_portal/integrations/ha_client.py` (GREEN 🟢 — T012 passes)

**Checkpoint**: Foundation ready — HA entity discovery available for all user stories

---

## Phase 3: User Story 1 — Select Integration from Auto-Detected List (Priority: P1) 🎯 MVP

**Goal**: Replace the free-text Integration ID input with a dropdown populated by auto-detected Rental Control integrations from Home Assistant

**Independent Test**: Visit `/admin/integrations/`, confirm the dropdown appears with correct entries from HA, select one, save, and verify the `HAIntegrationConfig` row is created with the correct `integration_id`

### Tests for User Story 1 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T014 [P] [US1] Write failing unit test for `auth_attribute` → `identifier_attr` bug fix in `tests/unit/test_integrations_ui_identifier_attr.py` — verify that `save_integration` route converts the `auth_attribute` form field value to `IdentifierAttr` enum and assigns to `identifier_attr` model field; test both create and update code paths; verify `slot_code`, `slot_name`, and `last_four` string values map to correct enum members (RED 🔴)
- [ ] T015 [P] [US1] Write failing integration test for `GET /api/integrations/discover` endpoint in `tests/integration/test_discover_endpoint.py` — test: (a) authenticated admin receives `DiscoveryResult` JSON with `available: true` and `integrations` list containing correct `DiscoveredIntegration` fields, (b) unauthenticated request gets 401/403, (c) when HA is unreachable endpoint returns `DiscoveryResult` with `available: false`, `error_message` (safe string), and `error_category` with HTTP 200, (d) response body never contains tokens or internal URLs (RED 🔴)
- [ ] T016 [P] [US1] Write failing integration test for `list_integrations` with discovery context in `tests/integration/test_integrations_ui_discovery.py` — verify template context receives `discovery_result` (`DiscoveryResult` object with `available`, `integrations`, `error_message`); when HA available: rendered HTML contains `<select>` dropdown with integration options; when HA unavailable: `discovery_result.available=False` and `discovery_result.error_message` safe message is set in context (RED 🔴)

### Implementation for User Story 1 (GREEN) 🟢

- [ ] T017 [US1] Fix `auth_attribute` → `identifier_attr` bug in `addon/src/captive_portal/api/routes/integrations_ui.py` — lines 106, 118, 143, 159 use `auth_attribute` but model field is `identifier_attr`; convert string to `IdentifierAttr` enum before assignment; fix both create and update paths to use the correct field name (GREEN 🟢 — T014 passes)
- [ ] T018 [US1] Add discovery API endpoint `GET /api/integrations/discover` in `addon/src/captive_portal/api/routes/integrations.py` — admin-only; calls `HADiscoveryService.discover()`, returns `DiscoveryResult` as JSON (contains `available`, `integrations`, `error_message`, `error_category`); always HTTP 200 (not 5xx, since the UI handles graceful degradation); on `HADiscoveryError` the `DiscoveryResult` has `available=False` with safe `error_message` and machine-readable `error_category`; update `addon/src/captive_portal/app.py` `create_app()` to include/mount the `integrations` router so `/api/integrations/discover` is reachable, and align the DB session dependency for `integrations.py` with the rest of the app (GREEN 🟢 — T015 passes)
- [ ] T019 [US1] Update `list_integrations` route in `addon/src/captive_portal/api/routes/integrations_ui.py` — call `HADiscoveryService.discover()` which returns `DiscoveryResult`; pass `discovery_result` to template context (contains `available`, `integrations`, `error_message`, `error_category`); template uses `discovery_result.available` to choose between pick-list and manual fallback (GREEN 🟢 — T016 passes)
- [ ] T020 [US1] Rewrite the "Add Integration" form in `addon/src/captive_portal/web/templates/admin/integrations.html` — when `discovery_result.available` is true and integrations exist, render a `<select>` dropdown populated with `discovery_result.integrations` (value = full `entity_id` per FR-011 and research R4, label = `friendly_name`); mark entries where `already_configured` is true as disabled with "(already added)" suffix; rename the existing `auth_attribute` dropdown field in this template to `identifier_attr` so it matches the `HAIntegrationConfig.identifier_attr` model field, keeping its behavior unchanged; keep the `checkout_grace_minutes` field behavior unchanged as well
- [ ] T021 [US1] Add `admin-integrations.js` in `addon/src/captive_portal/web/themes/default/admin-integrations.js` — on page load if the `<select>` dropdown exists, attach change handler to populate hidden `integration_id` input with selected value; disable submit when selection is "(already added)"; include `<script>` tag in `integrations.html`
- [ ] T022 [US1] Write failing integration test for `save_integration` accepting dropdown selection in `tests/integration/test_save_integration_dropdown.py` — verify: (a) save accepts `integration_id` from dropdown selection and creates `HAIntegrationConfig` row, (b) save accepts `integration_id` from manual text input, (c) 409 Conflict guard when auto-detected `integration_id` is already configured, (d) audit log records source (auto-detected vs manual), (e) form submits `identifier_attr` (field renamed from legacy `auth_attribute`) and it is persisted to `HAIntegrationConfig.identifier_attr` (RED 🔴)
- [ ] T023 [US1] Update `save_integration` route in `addon/src/captive_portal/api/routes/integrations_ui.py` — accept `integration_id` from either dropdown selection or manual text input; validate that auto-detected `integration_id` is not already configured (409 Conflict guard); audit log the source (auto-detected vs manual); read `identifier_attr` from the form (field name renamed from `auth_attribute`) and persist it to `HAIntegrationConfig.identifier_attr` (GREEN 🟢 — T022 passes)

**Checkpoint**: User Story 1 is fully functional — admin can select an integration from the auto-detected dropdown and save it

---

## Phase 4: User Story 2 — View Entity State Details Before Selecting (Priority: P2)

**Goal**: Enrich each pick-list entry with live entity state information (active booking indicator, calendar status, next event) so admins can distinguish between similar integrations

**Independent Test**: Load `/admin/integrations/` when HA has Rental Control integrations with and without active bookings; verify each entry shows an active booking indicator (e.g., "Active booking" vs "No active bookings"), state (active/idle), and next event summary

### Tests for User Story 2 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T024 [P] [US2] Write failing unit tests for enriched `DiscoveredIntegration` fields in `tests/unit/integrations/test_discovered_integration_enriched.py` — verify `next_event_summary: Optional[str]` and `next_checkin_date: Optional[str]` fields exist, default to `None`, serialize correctly in JSON output, and accept string values (RED 🔴)
- [ ] T025 [P] [US2] Write failing unit tests for enhanced entity state extraction in `tests/unit/integrations/test_discovery_state_extraction.py` — verify `HADiscoveryService` reads `state` ("on"/"off") to derive `state_display`; extracts `event_summary` from `attributes.message`; extracts `event_start` from `attributes.start_time` and `event_end` from `attributes.end_time`; populates `next_event_summary` and `next_checkin_date` from these attributes; verify state mapping: "on" → "Active booking", "off" → "No active bookings", "unavailable" → "Unavailable" (RED 🔴)

### Implementation for User Story 2 (GREEN) 🟢

- [ ] T026 [P] [US2] Extend `DiscoveredIntegration` model in `addon/src/captive_portal/integrations/ha_discovery_service.py` — add `next_event_summary: Optional[str] = None`, `next_checkin_date: Optional[str] = None`; these are populated from `attributes.message` and `attributes.start_time` respectively (GREEN 🟢 — T024 passes)
- [ ] T027 [US2] Enhance entity state extraction in `addon/src/captive_portal/integrations/ha_discovery_service.py` — read `state` ("on"/"off"/"unavailable") to derive `state_display`; extract `event_summary` from `attributes.message` (contains guest name + booking code when state is "on"); extract `event_start` from `attributes.start_time` and `event_end` from `attributes.end_time`; populate `next_event_summary` and `next_checkin_date` from these fields (GREEN 🟢 — T025 passes)
- [ ] T028 [US2] Update the dropdown rendering in `addon/src/captive_portal/web/templates/admin/integrations.html` — replace simple `<select>` with a rich pick-list (styled `<div>` list or enhanced `<select>` with `<optgroup>`) showing: friendly name, state badge (active/idle), and next event summary for each entry
- [ ] T029 [US2] Add CSS styles for the integration pick-list in `addon/src/captive_portal/web/themes/default/admin.css` — style state badges (green for active, grey for idle), next-event subtitle text, and "(already added)" disabled state; ensure responsive layout for enriched list items

**Checkpoint**: User Stories 1 AND 2 are functional — dropdown shows live state details for each integration

---

## Phase 5: User Story 3 — Fall Back to Manual Entry (Priority: P3)

**Goal**: When the HA API is unreachable, show a clear notification and fall back to the original manual text input field so the admin is never blocked

**Independent Test**: Simulate an unreachable HA API (invalid token, network timeout); verify the integrations page shows a notification banner and manual text input; submit a manual integration ID and confirm it saves correctly

### Tests for User Story 3 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T030 [P] [US3] Write failing integration test for fallback behavior in `tests/integration/test_integrations_ui_fallback.py` — mock `HAClient` to raise `HAConnectionError`; verify rendered page contains notification banner with safe error message (no tokens), `data-error-type` attribute, and a manual `<input type="text">` for `integration_id`; test each error type: connection, authentication, timeout, server error (RED 🔴)
- [ ] T031 [P] [US3] Write failing integration test for zero integrations empty state in `tests/integration/test_integrations_ui_empty_state.py` — mock `HAClient` returning empty list; verify rendered page shows empty-state message ("No Rental Control integrations found in Home Assistant. Please install one first.") and includes manual entry fallback below it (RED 🔴)
- [ ] T032 [P] [US3] Write failing integration test for manual save path preservation in `tests/integration/test_save_integration_manual.py` — verify submitting `integration_id` via manual text input (no dropdown) creates `HAIntegrationConfig` row with correct fields; same validation rules, same audit logging as current implementation (RED 🔴)

### Implementation for User Story 3 (GREEN) 🟢

- [ ] T033 [US3] Add fallback rendering in `addon/src/captive_portal/web/templates/admin/integrations.html` — when `discovery_result.available` is false, display notification banner with `discovery_result.error_message` (safe, no secrets) and render manual `<input type="text">` for `integration_id`; use `{% if discovery_result.available %}...{% else %}...{% endif %}`; set `data-error-type` attribute from `discovery_result.error_category` for CSS differentiation (GREEN 🟢 — T030 passes)
- [ ] T034 [US3] Handle edge case: zero Rental Control integrations detected in `addon/src/captive_portal/web/templates/admin/integrations.html` — when `discovery_result.available` is true but `discovery_result.integrations` is empty, display empty-state message ("No Rental Control integrations found in Home Assistant. Please install one first.") and show manual entry fallback below it (GREEN 🟢 — T031 passes)
- [ ] T035 [US3] Style notification banner in `addon/src/captive_portal/web/themes/default/admin.css` — warning/info alert box with icon, constrained width, clear typography; differentiate between timeout, authentication error, and connection refused via `data-error-type` attribute
- [ ] T036 [US3] Ensure `save_integration` in `addon/src/captive_portal/api/routes/integrations_ui.py` handles manual text input identically to current implementation — when form submits `integration_id` from text input (no dropdown), the save flow must work exactly as it does today with same validation and same audit logging (GREEN 🟢 — T032 passes)

**Checkpoint**: User Stories 1, 2, AND 3 are functional — graceful degradation works when HA is unavailable

---

## Phase 6: User Story 4 — Refresh Available Integrations (Priority: P4)

**Goal**: Provide a refresh control that re-queries HA without a full page reload so the admin can discover newly-added integrations mid-session

**Independent Test**: Load the integrations page, add a new Rental Control integration in HA, click the refresh button, verify the new integration appears in the list without a page reload

### Tests for User Story 4 (RED) 🔴

> **Write these tests FIRST; confirm they FAIL before implementing production code**

- [ ] T037 [US4] Write failing integration test for refresh triggering re-discovery in `tests/integration/test_integrations_refresh.py` — verify: (a) AJAX `GET /api/integrations/discover` returns updated list after HA state changes, (b) loading state is communicated (endpoint responds promptly), (c) when refresh fails endpoint returns error payload allowing JS to show fallback notification (RED 🔴)

### Implementation for User Story 4 (GREEN) 🟢

- [ ] T038 [US4] Add refresh button to `addon/src/captive_portal/web/templates/admin/integrations.html` — place next to pick-list heading; button triggers AJAX call to `GET /api/integrations/discover`; show loading spinner while request is in progress (GREEN 🟢 — T037 passes, endpoint behavior verified)
- [ ] T039 [US4] Implement AJAX refresh logic in `addon/src/captive_portal/web/themes/default/admin-integrations.js` — on refresh click: show spinner, call `GET /api/integrations/discover`; for consistency with existing `CSRFProtection`, include the `X-CSRF-Token` header using the same token source as other AJAX requests (even though the discovery endpoint itself does not enforce CSRF on this read-only GET); on success re-render pick-list with updated entries, on failure show inline notification banner and switch to manual entry fallback; handle both JSON success and error payloads
- [ ] T040 [US4] Add loading indicator CSS in `addon/src/captive_portal/web/themes/default/admin.css` — spinner animation for refresh button, disabled state while loading, smooth transition when pick-list updates

**Checkpoint**: All four user stories are functional and independently testable

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Acceptance tests, performance tests, edge-case tests, documentation, OpenAPI, and code quality enforcement

### Acceptance, Performance & Edge-Case Tests

- [ ] T041 [P] Write acceptance tests for success criteria SC-001 through SC-006 in `tests/integration/test_discovery_acceptance.py` — SC-001: end-to-end add-integration flow completes successfully; SC-002/SC-003: pick-list selection yields correct `integration_id` with no typo possibility; SC-004: fallback presented when HA unreachable (mock timeout at 10s); SC-005: discovery completes within expected time; SC-006: all HA Rental Control integrations appear in list (mock 5 entities, verify 5 returned)
- [ ] T042 [P] Write performance test for 5-second discovery target (SC-005) in `tests/performance/test_discovery_performance.py` — use `@pytest.mark.performance` marker; mock HA API with realistic payload (10+ entities with full state and attributes); assert `HADiscoveryService.discover()` completes in < 5s; use `async_client` fixture for async timing
- [ ] T043 [P] Write edge-case tests in `tests/integration/test_discovery_edge_cases.py` — EC-3: mock an integration that was previously added to captive portal but is now removed from HA; verify it no longer appears in the discovery pick-list but the existing `HAIntegrationConfig` row remains intact and functional; EC-5: mock 20+ Rental Control integrations; verify all 20+ entries are returned by the discovery endpoint and the rendered pick-list contains all entries (scrollability verified by presence in HTML)

### Documentation & OpenAPI

- [ ] T044 [P] Add OpenAPI documentation for `GET /api/integrations/discover` endpoint in `addon/src/captive_portal/api/routes/integrations.py` — add `summary`, `description`, `response_model` (using `DiscoveryResult`), and `responses` dict (200 success with `DiscoveryResult` containing integration list, 200 unavailable with `available=false`, `error_message`, `error_category`) to the route decorator; ensure Swagger UI at `/docs` shows the discovery endpoint with example request/response payloads
- [ ] T045 [P] Add structured logging for discovery operations in `addon/src/captive_portal/integrations/ha_discovery_service.py` — log discovery attempts (entity count, duration in ms), errors (full detail including HTTP status, response body snippet), and fallback triggers; use existing `logger` pattern with `extra={}` structured data
- [ ] T046 [P] Update `addon/config.yaml` — add or update schema entries for all settings that participate in `_ADDON_OPTION_MAP`, including `ha_base_url` and `ha_token` if they are intended to be configurable addon options (otherwise clarify in T004 that these are env-only and not exposed as addon options), and any additional options needed for discovery (e.g., `ha_discovery_timeout`); ensure each is present in the `schema` section with appropriate type and validation constraints
- [ ] T047 [P] Add documentation section to `docs/ha_integration_guide.md` — document the auto-detection feature, fallback behavior, refresh control, and troubleshooting tips for common API errors (401 unauthorized, timeout, connection refused)

### Code Quality & Compliance

- [ ] T048 Verify REUSE compliance for all new files — ensure every new `.py`, `.js`, `.html`, `.css` file has `SPDX-FileCopyrightText` and `SPDX-License-Identifier` headers; run `reuse lint` to confirm zero violations
- [ ] T049 Run full linting, type-checking, and docstring coverage — execute `ruff check addon/src/`, `mypy addon/src/captive_portal/` (strict mode), and `interrogate addon/src/captive_portal/` (fail-under=100); fix any issues in new code; verify zero errors/warnings across all three tools
- [ ] T050 Manual end-to-end validation — walk through all four user stories sequentially: (1) auto-detect and select, (2) verify state details are displayed, (3) simulate HA unavailable and use manual entry, (4) refresh after adding a new HA integration; verify each story works independently

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phases 3–6)**: All depend on Foundational phase completion
  - User stories proceed in priority order (P1 → P2 → P3 → P4)
  - US2 builds on US1's dropdown (sequential)
  - US3 adds fallback to US1's page (sequential after US1)
  - US4 adds refresh to US1+US2's pick-list (sequential after US2)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependencies on other stories
- **User Story 2 (P2)**: Depends on US1's dropdown rendering (T020, T021) — enhances the pick-list
- **User Story 3 (P3)**: Depends on US1's template structure (T020) — adds fallback branch to same template
- **User Story 4 (P4)**: Depends on US1's API endpoint (T018) and US2's rich list rendering (T028) — adds AJAX refresh

### Within Each User Story (TDD Cycle)

1. 🔴 **RED**: Write failing tests FIRST — confirm they fail
2. 🟢 **GREEN**: Write minimum production code to make tests pass
3. ♻️ **REFACTOR**: Clean up while keeping tests green
4. Models before services
5. Services before API routes
6. API routes before UI templates
7. Templates before JavaScript behavior
8. **CI tests MUST pass before manual testing** (constitution §II)

### Parallel Opportunities

- T002 and T003 can run in parallel (different test files)
- T004 and T005 can run in parallel (different production files)
- T006, T007, and T008 can run in parallel (different test files)
- T009 and T010 can run in parallel (different production files)
- T014, T015, and T016 can run in parallel (different US1 test files)
- T024 and T025 can run in parallel (different US2 test files)
- T026 runs before T027 (both target ha_discovery_service.py; model extension before service enhancement)
- T030, T031, and T032 can run in parallel (different US3 test files)
- T041, T042, T043, T044, T045, T046, T047 can all run in parallel

---

## Parallel Example: Phase 1 Setup

```text
# RED — Launch test tasks in parallel:
Task T002: "Write failing tests for HA settings fields in tests/unit/config/test_settings_ha_fields.py"
Task T003: "Write failing tests for DiscoveredIntegration model in tests/unit/integrations/test_discovered_integration_model.py"

# GREEN — Launch implementation in parallel (after RED confirmed failing):
Task T004: "Add HA settings to AppSettings in settings.py"
Task T005: "Create DiscoveredIntegration and DiscoveryResult Pydantic models in ha_discovery_service.py"
```

## Parallel Example: Phase 2 Foundational

```text
# RED — Launch all test tasks in parallel:
Task T006: "Write failing tests for HADiscoveryError hierarchy in tests/unit/integrations/test_ha_discovery_errors.py"
Task T007: "Write failing tests for get_all_states in tests/unit/integrations/test_ha_client_discovery.py"
Task T008: "Write failing tests for HADiscoveryService in tests/unit/integrations/test_ha_discovery_service.py"
Task T012: "Write failing test for HAClient dependency in tests/unit/integrations/test_ha_client_dependency.py"

# GREEN — Launch implementations in parallel (after RED confirmed failing):
Task T009: "Create HADiscoveryError exception hierarchy in ha_errors.py"
Task T010: "Add get_all_states to ha_client.py"

# Then sequential (depends on T009, T010):
Task T011: "Create HADiscoveryService in ha_discovery_service.py"
Task T013: "Register HAClient as FastAPI dependency in app.py"
```

## Parallel Example: Phase 3 User Story 1

```text
# RED — Launch all US1 test tasks in parallel:
Task T014: "Write failing test for identifier_attr bug in tests/unit/test_integrations_ui_identifier_attr.py"
Task T015: "Write failing test for discover endpoint in tests/integration/test_discover_endpoint.py"
Task T016: "Write failing test for list_integrations discovery in tests/integration/test_integrations_ui_discovery.py"

# GREEN — Fix bug first (before template rewrite):
Task T017: "Fix auth_attribute → identifier_attr bug in integrations_ui.py"

# GREEN — Then implement endpoint and route:
Task T018: "Add GET /api/integrations/discover endpoint in integrations.py"
Task T019: "Update list_integrations route in integrations_ui.py"

# Then template and JS (sequential):
Task T020: "Rewrite Add Integration form in integrations.html"
Task T021: "Add admin-integrations.js for dropdown behavior"

# RED then GREEN for save logic:
Task T022: "Write failing test for save_integration dropdown in tests/integration/test_save_integration_dropdown.py"
Task T023: "Update save_integration route in integrations_ui.py"
```

## Parallel Example: Phase 4 User Story 2

```text
# RED — Launch test tasks in parallel:
Task T024: "Write failing tests for enriched DiscoveredIntegration in tests/unit/integrations/test_discovered_integration_enriched.py"
Task T025: "Write failing tests for enhanced state extraction in tests/unit/integrations/test_discovery_state_extraction.py"

# GREEN — Sequential (both target ha_discovery_service.py):
Task T026: "Extend DiscoveredIntegration model"
Task T027: "Enhance entity state extraction in discovery service"

# Then sequential:
Task T028: "Update dropdown rendering in integrations.html"
Task T029: "Add CSS styles for pick-list in admin.css"
```

## Parallel Example: Phase 7 Polish

```text
# Launch all independent tasks in parallel:
Task T041: "Write acceptance tests for SC-001 through SC-006"
Task T042: "Write performance test for 5-second discovery target"
Task T043: "Write edge-case tests for EC-3 and EC-5"
Task T044: "Add OpenAPI documentation for discover endpoint"
Task T045: "Add structured logging for discovery operations"
Task T046: "Update addon/config.yaml"
Task T047: "Add documentation to ha_integration_guide.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T005) — RED then GREEN
2. Complete Phase 2: Foundational (T006–T013) — RED then GREEN
3. Complete Phase 3: User Story 1 (T014–T023) — RED then GREEN
4. **STOP and VALIDATE**: Run `pytest tests/unit/ tests/integration/ -v` — all tests GREEN
5. Deploy/demo if ready — admin can already use the dropdown instead of free-text input

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready, all foundational tests GREEN
2. Add User Story 1 → Tests GREEN → Deploy/Demo (MVP!)
3. Add User Story 2 → Tests GREEN → Deploy/Demo (enriched pick-list)
4. Add User Story 3 → Tests GREEN → Deploy/Demo (fallback resilience)
5. Add User Story 4 → Tests GREEN → Deploy/Demo (refresh convenience)
6. Polish → Acceptance/performance/edge-case tests GREEN → Final quality gate
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
2. Once Foundational is done:
   - Developer A: User Story 1 (P1) — must complete first due to dependencies
   - After US1 complete: Developer A → User Story 3, Developer B → User Story 2
   - After US2 complete: Developer B → User Story 4
3. Stories integrate incrementally

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- **TDD is non-negotiable** — every production code task references which RED test it makes GREEN
- The `auth_attribute` → `identifier_attr` bug fix (T017) is ordered BEFORE the template rewrite (T020) to ensure the save path is correct before UI changes build on it
- `DiscoveredIntegration` is a transient Pydantic model — NOT a SQLModel table; it is never persisted
- The HA API token is available via `SUPERVISOR_TOKEN` environment variable in the addon runtime (set by HA Supervisor when `homeassistant_api: true`)
- Performance test (T042) targets SC-005: 5-second discovery completion under normal conditions
- Edge-case tests (T043) cover EC-3 (integration removed from HA) and EC-5 (20+ integrations scrollability)
- Acceptance tests (T041) verify all six success criteria (SC-001 through SC-006)
- OpenAPI documentation (T044) ensures `GET /api/integrations/discover` is self-documenting in Swagger UI
- `interrogate` at 100% docstring coverage is enforced alongside `ruff` and `mypy` in T049 (constitution requirement)
- Commit after each task or logical RED+GREEN pair; all commits require DCO sign-off (`git commit -s`)
- Stop at any checkpoint to validate story independently
