SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Tasks: Guest Portal Decomposition

**Input**: Design documents from
`/specs/014-guest-portal-decomposition/`
**Prerequisites**: spec.md (user stories P1-P3), plan.md, research.md,
data-model.md, quickstart.md, contracts/guest-http-contract.md

**Tests**: TDD is MANDATORY per project constitution §II. This feature is a
behavior-preserving refactor, so characterization tests are written first and
must pass on the current pre-refactor code before production code moves. New
helper modules still follow Red-Green-Refactor: write the focused test first,
confirm it fails because the helper boundary does not exist yet, then extract
production code while keeping the characterization suite unchanged.

**Organization**: Tasks are grouped by phases that preserve the settled order:
first characterize the current guest portal behavior, then decompose cohesive
units, then clear complexity findings and run quality gates.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task supports (US1, US2, US3)
- 🟢 = BASELINE/GREEN characterization · 🔴 = RED helper-boundary test ·
  ♻️ = REFACTOR while keeping tests green
- Include exact file paths in descriptions

## Path Conventions

- **Guest route source**:
  `addon/src/captive_portal/api/routes/guest_portal.py`
- **Extracted helpers**:
  `addon/src/captive_portal/api/routes/guest_authorization/`
- **Guest templates**:
  `addon/src/captive_portal/web/templates/guest/`
- **Unit route tests**: `tests/unit/routes/`
- **Security tests**: `tests/unit/security/`
- **Guest integration tests**: `tests/integration/`
- **Test utilities**: `tests/utils/`
- **Complexity baseline**: `.aislop/baseline.json`
- **Out of scope**: `addon/src/captive_portal/api/routes/portal_settings_ui.py`
  and the known `portal_settings_ui.py:110` parameter-count finding

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Start implementation from the merged spec and plan while proving
that task execution is limited to the guest portal decomposition scope.

- [ ] T001 Create implementation branch `014-guest-portal-decomposition` from
  `main`; confirm `specs/014-guest-portal-decomposition/` contains `spec.md`,
  `plan.md`, `research.md`, `data-model.md`, `quickstart.md`,
  `contracts/guest-http-contract.md`, and this `tasks.md`

- [ ] T002 [US1] Confirm the live source inventory in
  `addon/src/captive_portal/api/routes/guest_portal.py` still includes
  `_truncate`, `_apply_site_override`, `_sanitize_error_message`,
  `_authorize_with_controller`, `_handle_get_submission`,
  `show_authorize_form`, `_extract_mac_address`, `_process_authorization`,
  `handle_authorization`, `show_welcome`, and `show_error`; do not move
  production code before Phase 2 is green

---

## Phase 2: Foundational — Characterization First (Blocking)

**Purpose**: Pin current externally observable behavior before any production
code movement. These tests are expected to pass on current code after dynamic
CSRF tokens, timestamps, generated grant IDs, cookies, controller IDs, and audit
timestamps are normalized explicitly.

**⚠️ CRITICAL**: No decomposition or complexity refactor may begin until T003
through T014 are complete and T015 is green on unmodified production code.

### Characterization for Current Behavior (BASELINE/GREEN) 🟢

> **Write these tests FIRST; confirm they PASS against the current
> `guest_portal.py` before moving production code**

- [ ] T003 [P] [US1] Create golden normalization helpers in
  `tests/utils/guest_portal_characterization.py` for replacing only dynamic
  CSRF token values, generated grant IDs, `grant_id` cookie values, controller
  grant IDs, ISO timestamps, and audit timestamps while preserving stable HTTP
  bodies, headers, redirects, cookies attributes, audit metadata, grant fields,
  and controller payloads exactly

- [ ] T004 [P] [US1] Extend
  `tests/integration/test_guest_portal_form_flow.py` to characterize
  `GET /guest/authorize` form rendering with `clientMac`, `clientIp`, `site`,
  `apMac`, `gatewayMac`, `radioId`, `ssidName`, `vid`, `t`, `redirectUrl`,
  `continue`, hidden fields, GET form method, generated CSRF token presence,
  effective continue selection, debug redaction, content type, status code, and
  route-level security headers

- [ ] T005 [P] [US1] Extend
  `tests/integration/test_guest_authorization_flow_voucher.py` to characterize
  successful voucher authorization, GET submission with `code` and `csrf_token`,
  POST submission, expired/revoked vouchers, invalid voucher format,
  device-limit failures, duplicate-device behavior, voucher VLAN denial,
  persisted `AccessGrant` fields, audit entries, controller payload, 303
  redirect, safe continue handling, and `grant_id` cookie attributes

- [ ] T006 [P] [US1] Extend
  `tests/integration/test_guest_authorization_flow_booking.py` to characterize
  successful booking authorization, missing integration, booking not found,
  outside-window denial, duplicate active grants, grace-period handling,
  case-preserved booking references, original user input, integration IDs,
  booking VLAN denial, audit metadata, controller payload, 303 redirect, and
  `grant_id` cookie attributes

- [ ] T007 [P] [US1] Extend `tests/unit/security/test_hmac_csrf.py` and guest
  route integration coverage to characterize CSRF extraction from GET query
  parameters, POST form data, and `X-CSRF-Token`; missing, malformed, expired,
  tampered, Origin-mismatched, and Referer-mismatched CSRF failures must keep
  current status codes, sanitized guest-facing HTML, retry links, and audit
  behavior

- [ ] T008 [P] [US1] Extend
  `tests/unit/routes/test_guest_portal_mac_extraction.py` to characterize MAC
  priority order across `X-MAC-Address`, `X-Client-Mac`, `Client-MAC`, submitted
  form MAC, and `clientMac` query; include dash-separated Omada normalization,
  invalid MAC HTTP 400 detail, missing MAC HTTP 400 detail, and MAC failure
  audit metadata

- [ ] T009 [P] [US1] Extend
  `tests/unit/routes/test_guest_portal_omada_params.py` and
  `tests/unit/routes/test_guest_portal_omada.py` to characterize Omada metadata
  pass-through, truncation lengths, retry-query keys, legacy site override for
  valid 12-64 character hex sites, invalid site preservation, no-adapter
  success, adapter authorize arguments, and `controller_grant_id` persistence

- [ ] T010 [P] [US1] Extend
  `tests/unit/routes/test_guest_portal_omada_errors.py` to characterize
  `OmadaClientError` and `OmadaRetryExhaustedError` handling, including FAILED
  grant status, sanitized HTTP 502 guest error, diagnostic-only detail, audit
  metadata, logging redaction, and absence of leaked controller internals

- [ ] T011 [P] [US1] Extend
  `tests/integration/test_guest_external_url.py`,
  `tests/integration/test_post_auth_redirect_fallback.py`,
  `tests/integration/test_post_auth_redirect_original_destination.py`, and
  `tests/integration/test_post_auth_redirect_whitelist.py` to characterize safe
  continue URLs, unsafe URL fallback, root-path-aware `/guest/welcome`, retry
  URL construction, and open-redirect protections

- [ ] T012 [P] [US1] Extend
  `tests/integration/test_guest_security_headers.py`,
  `tests/integration/test_guest_portal_full_rendering.py`, and
  `tests/unit/test_guest_error_handler.py` to characterize `/guest/welcome` and
  `/guest/error` rendering, sanitized error messages, 500-character truncation,
  root-path-aware retry URLs, content type, cache headers, CSP fallback,
  `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy`

- [ ] T013 [P] [US1] Extend
  `tests/integration/test_rate_limit_enforcement.py` and
  `tests/unit/security/test_rate_limiter.py` to characterize trusted-proxy-aware
  client IP resolution, rate-limit denial, `Retry-After`, rate-limit audit
  metadata, and successful rate-limit clearing after authorization

- [ ] T014 [P] [US1] Extend
  `tests/integration/test_vlan_voucher_authorization.py` and
  `tests/integration/test_vlan_booking_authorization.py` to characterize voucher
  and booking VLAN allowlist decisions, audit metadata, HTTP 403 behavior, and
  absence or presence of controller calls on denial

- [ ] T015 [US1] Run the complete characterization baseline on current code and
  confirm it is green before production movement:

  ```bash
  uv run pytest \
    tests/integration/test_guest_portal_form_flow.py \
    tests/integration/test_guest_authorization_flow_voucher.py \
    tests/integration/test_guest_authorization_flow_booking.py \
    tests/integration/test_guest_external_url.py \
    tests/integration/test_post_auth_redirect_fallback.py \
    tests/integration/test_post_auth_redirect_original_destination.py \
    tests/integration/test_post_auth_redirect_whitelist.py \
    tests/integration/test_guest_security_headers.py \
    tests/integration/test_guest_portal_full_rendering.py \
    tests/integration/test_rate_limit_enforcement.py \
    tests/integration/test_vlan_voucher_authorization.py \
    tests/integration/test_vlan_booking_authorization.py \
    tests/unit/routes/test_guest_portal_mac_extraction.py \
    tests/unit/routes/test_guest_portal_omada.py \
    tests/unit/routes/test_guest_portal_omada_errors.py \
    tests/unit/routes/test_guest_portal_omada_params.py \
    tests/unit/security/test_hmac_csrf.py \
    tests/unit/security/test_rate_limiter.py \
    tests/unit/test_guest_error_handler.py \
    -v
  ```

**Checkpoint**: Characterization evidence is green against the pre-refactor
implementation. Production code may now be decomposed, but expected outputs must
remain unchanged.

---

## Phase 3: User Story 1 — Preserve Guest Authorization Behavior (Priority: P1) 🎯 MVP

**Goal**: Extract cohesive helper units while `/guest/authorize` GET and POST,
`/guest/welcome`, `/guest/error`, grants, audit records, redirects, cookies,
security headers, and controller calls remain behavior-equivalent.

**Independent Test**: Run the unchanged characterization suite after each helper
extraction and verify byte-for-byte equivalence for all stable outputs.

### Tests for Helper Boundaries (RED) 🔴

> **Write each focused helper-boundary test before extracting the helper; the
> characterization suite from Phase 2 remains the golden contract.**

- [ ] T016 [P] [US1] Write failing context grouping tests in
  `tests/unit/routes/test_guest_authorization_context.py` for `GuestOmadaParams`,
  `GuestAuthorizationDependencies`, `GuestAuthorizationContext`, and
  `AuthorizationDecisionResult` preserving query/form aliases, empty-value
  handling, retry-query keys, dependency override behavior, and grant/audit flow
  state (RED 🔴)

- [ ] T017 [P] [US1] Write failing form helper tests in
  `tests/unit/routes/test_guest_authorization_form.py` for GET submission
  detection, Omada hidden-field context, effective continue selection,
  root-path-aware fallback, debug redaction, CSRF token insertion, and route
  security headers (RED 🔴)

- [ ] T018 [P] [US1] Write failing MAC helper compatibility tests in
  `tests/unit/routes/test_guest_portal_mac_extraction.py` verifying the extracted
  helper preserves current priority order, normalization, HTTP 400 details, and
  import compatibility for existing guest route tests (RED 🔴)

- [ ] T019 [P] [US1] Write failing controller helper tests in
  `tests/unit/routes/test_guest_authorization_controller.py` for `_truncate`,
  legacy site override, no-adapter success, adapter authorize payloads,
  controller grant ID storage, failed status transitions, diagnostic-only error
  detail, and secret-safe logging (RED 🔴)

- [ ] T020 [P] [US1] Write failing redirect and error helper tests in
  `tests/unit/routes/test_guest_authorization_redirects.py` and
  `tests/unit/routes/test_guest_authorization_errors.py` for safe continue
  validation, fallback `/guest/welcome`, retry URL construction,
  `grant_id` cookie attributes, sanitized error messages, default error text,
  tag stripping, and route security headers (RED 🔴)

### Implementation for User Story 1 (GREEN/REFACTOR) 🟢♻️

- [ ] T021 [US1] Create
  `addon/src/captive_portal/api/routes/guest_authorization/__init__.py` and
  `addon/src/captive_portal/api/routes/guest_authorization/context.py` with SPDX
  headers, typed data carriers, and docstrings for Omada metadata,
  authorization dependencies, per-request context, and decision results; update
  `guest_portal.py` to group internal values without changing FastAPI-visible
  route parameters or accepted fields (GREEN 🟢 — T016 passes)

- [ ] T022 [US1] Extract GET form rendering, submission detection, hidden Omada
  context, effective continue selection, debug redaction, CSRF form context, and
  route security header helpers into
  `addon/src/captive_portal/api/routes/guest_authorization/form.py`; keep
  `show_authorize_form` response bodies, headers, status codes, and aliases
  unchanged (GREEN 🟢 — T017 passes)

- [ ] T023 [US1] Extract MAC extraction and normalization into
  `addon/src/captive_portal/api/routes/guest_authorization/mac_address.py`; keep
  existing route-level wrapper or import compatibility in `guest_portal.py` so
  current tests and private helper users retain behavior (GREEN 🟢 — T018
  passes)

- [ ] T024 [US1] Extract `_truncate`, legacy Omada site override, and controller
  authorization behavior into
  `addon/src/captive_portal/api/routes/guest_authorization/controller.py`; keep
  no-adapter success, adapter payloads, grant status transitions, commits,
  refreshes, `controller_grant_id`, audit detail, and logging behavior unchanged
  (GREEN 🟢 — T019 passes)

- [ ] T025 [US1] Extract redirect construction and sanitized guest error helpers
  into `addon/src/captive_portal/api/routes/guest_authorization/redirects.py` and
  `addon/src/captive_portal/api/routes/guest_authorization/errors.py`; preserve
  success 303 responses, `grant_id` cookies, retry links, root-path awareness,
  HTML error pages, and security headers (GREEN 🟢 — T020 passes)

- [ ] T026 [US1] Run the unchanged Phase 2 characterization command after the
  low-risk extraction tasks T021-T025 and fix only behavior regressions within
  `guest_portal.py`, `guest_authorization/`, or characterization tests that were
  incorrect about pre-refactor behavior

**Checkpoint**: Form rendering, MAC extraction, controller authorization,
redirects, and error handling are extracted with unchanged guest behavior.

---

## Phase 4: User Story 1 — Voucher and Booking Flow Extraction (Priority: P1)

**Goal**: Split `_process_authorization` decision logic into voucher and booking
units while preserving the exact authorization sequence from the HTTP contract.

**Independent Test**: Voucher and booking characterization tests pass unchanged
before and after flow extraction.

### Tests for Decision Helpers (RED) 🔴

- [ ] T027 [P] [US1] Write failing voucher flow helper tests in
  `tests/unit/routes/test_guest_authorization_vouchers.py` for voucher format
  validation, service lookup/redemption calls, VLAN validation order,
  device-limit denial, redemption failure, duplicate-device behavior, grant
  field preservation, target metadata, and audit intent (RED 🔴)

- [ ] T028 [P] [US1] Write failing booking flow helper tests in
  `tests/unit/routes/test_guest_authorization_bookings.py` for integration
  lookup across configured integrations, no-integration HTTP 503, not-found HTTP
  404, outside-window HTTP 403, duplicate active grant HTTP 409, grace-period
  bounds, case-preserved booking references, `user_input_code`, `integration_id`,
  VLAN validation, and audit intent (RED 🔴)

### Implementation for Decision Helpers (GREEN/REFACTOR) 🟢♻️

- [ ] T029 [US1] Extract voucher validation, VLAN checking, redemption, grant
  field handling, exception mapping, and audit metadata into
  `addon/src/captive_portal/api/routes/guest_authorization/vouchers.py` while
  preserving current `VoucherService` calls and HTTP outcomes (GREEN 🟢 — T027
  passes)

- [ ] T030 [US1] Extract booking lookup, window checks, duplicate detection,
  VLAN checking, grant construction, exception mapping, and audit metadata into
  `addon/src/captive_portal/api/routes/guest_authorization/bookings.py` while
  preserving current repository and service behavior (GREEN 🟢 — T028 passes)

- [ ] T031 [US1] Refactor `_process_authorization` in
  `addon/src/captive_portal/api/routes/guest_portal.py` into a thin orchestrator
  that calls context, CSRF/rate-limit, MAC, voucher or booking, Omada metadata,
  controller, audit, and redirect helpers in the current observable order
  defined by `contracts/guest-http-contract.md` (REFACTOR ♻️)

- [ ] T032 [US1] Run the unchanged Phase 2 characterization command plus
  `uv run pytest tests/integration/test_authorize_end_to_end.py -v` and confirm
  voucher, booking, controller, grant, audit, redirect, cookie, CSRF, and MAC
  behavior remain green after T029-T031

**Checkpoint**: `_process_authorization` is behavior-preserving orchestration,
and voucher/booking decision behavior is discoverable in cohesive units.

---

## Phase 5: User Story 2 — Clear Complexity Findings Safely (Priority: P2)

**Goal**: Clear guest portal file/function complexity and C901 findings without
changing the public HTTP contract or touching out-of-scope settings code.

**Independent Test**: Ruff C901 and staged `aislop` complexity gates report no
unhandled guest portal findings; characterization tests remain green.

- [ ] T033 [US2] Reduce internal parameter counts in
  `addon/src/captive_portal/api/routes/guest_portal.py` and extracted helpers by
  using `GuestOmadaParams`, `GuestAuthorizationDependencies`, and related
  internal grouping; do not remove, rename, retype, or change any FastAPI-visible
  query parameters, form fields, aliases, defaults, optionality, or validation
  behavior

- [ ] T034 [US2] Remove `# noqa: C901` from `show_authorize_form` in
  `addon/src/captive_portal/api/routes/guest_portal.py` only after helper
  extraction and targeted ruff checks prove the function passes C901 while the
  GET form contract remains unchanged

- [ ] T035 [US2] Remove `# noqa: C901` from `_process_authorization` in
  `addon/src/captive_portal/api/routes/guest_portal.py` only after flow
  extraction and targeted ruff checks prove the orchestrator passes C901 while
  the authorization sequence remains unchanged

- [ ] T036 [US2] Run targeted complexity linting with
  `uv run ruff check addon/src/captive_portal/api/routes/ tests/unit/routes/`
  and confirm no C901 violation and no C901 suppression remains on
  `show_authorize_form` or `_process_authorization`

- [ ] T037 [US2] Run the staged `aislop` complexity gate and refresh
  `.aislop/baseline.json` only if required by the tool; confirm no unhandled
  `complexity/file-too-large` finding for `guest_portal.py`, no
  `complexity/function-too-long` finding for `_process_authorization`, and no
  unhandled guest portal `complexity/too-many-params` finding remains

- [ ] T038 [US2] If a FastAPI route parameter-count finding cannot be safely
  cleared without risking the pinned HTTP contract, document or baseline only
  that route finding with a reason linked to `contracts/guest-http-contract.md`;
  explicitly leave `addon/src/captive_portal/api/routes/portal_settings_ui.py`
  and `portal_settings_ui.py:110` unchanged and out of scope

- [ ] T039 [US2] Run the unchanged Phase 2 characterization command after T033
  through T038 and confirm complexity cleanup did not alter HTTP, audit, grant,
  cookie, redirect, CSRF, MAC, or controller behavior

**Checkpoint**: Guest portal complexity findings are cleared or safely
baselined, C901 suppressions are gone, and contract characterization is green.

---

## Phase 6: User Story 3 — Improve Future Review Safety (Priority: P3)

**Goal**: Make future guest authorization reviews smaller and safer by ensuring
each extracted unit has focused tests, docstrings, types, and clear behavioral
ownership.

**Independent Test**: A reviewer can map voucher validation, booking validation,
MAC extraction, controller authorization, redirect handling, and error/audit
behavior to a cohesive helper and a targeted test file.

- [ ] T040 [P] [US3] Ensure every new source file under
  `addon/src/captive_portal/api/routes/guest_authorization/` has the required
  SPDX headers, module docstring, function/class docstrings, and public type
  annotations required by constitution §I

- [ ] T041 [P] [US3] Ensure `tests/unit/routes/test_guest_authorization_context.py`,
  `tests/unit/routes/test_guest_authorization_form.py`,
  `tests/unit/routes/test_guest_authorization_vouchers.py`,
  `tests/unit/routes/test_guest_authorization_bookings.py`,
  `tests/unit/routes/test_guest_authorization_controller.py`,
  `tests/unit/routes/test_guest_authorization_redirects.py`, and
  `tests/unit/routes/test_guest_authorization_errors.py` each name the protected
  behavior they cover and fail clearly when their extracted unit regresses

- [ ] T042 [US3] Keep `addon/src/captive_portal/api/routes/guest_portal.py` as
  thin FastAPI route definitions plus compatibility wrappers only; verify it no
  longer owns voucher decisions, booking decisions, MAC extraction internals,
  controller authorization internals, redirect construction internals, or error
  sanitization internals

- [ ] T043 [US3] In the implementation PR description, include the
  characterization evidence map required by SC-007: extracted helper file,
  protected behavior, and targeted characterization or unit test path; do not add
  unrelated repository documentation files for this evidence

**Checkpoint**: The decomposed guest authorization flow is reviewable by
cohesive unit and protected by targeted tests plus the unchanged golden suite.

---

## Phase 7: Polish & Cross-Cutting Validation

**Purpose**: Run the smallest targeted gates first, then repository-level gates,
without broadening implementation scope.

- [ ] T044 [P] Run targeted guest regression tests from
  `specs/014-guest-portal-decomposition/quickstart.md`:

  ```bash
  uv run pytest \
    tests/integration/test_guest_portal_form_flow.py \
    tests/integration/test_guest_authorization_flow_voucher.py \
    tests/integration/test_guest_authorization_flow_booking.py \
    tests/integration/test_guest_external_url.py \
    tests/integration/test_post_auth_redirect_fallback.py \
    tests/integration/test_post_auth_redirect_original_destination.py \
    tests/integration/test_post_auth_redirect_whitelist.py \
    tests/integration/test_guest_security_headers.py \
    tests/integration/test_vlan_voucher_authorization.py \
    tests/integration/test_vlan_booking_authorization.py \
    tests/unit/routes/test_guest_portal_mac_extraction.py \
    tests/unit/routes/test_guest_portal_omada.py \
    tests/unit/routes/test_guest_portal_omada_errors.py \
    tests/unit/routes/test_guest_portal_omada_params.py \
    tests/unit/security/test_hmac_csrf.py \
    tests/unit/security/test_rate_limiter.py
  ```

- [ ] T045 [P] Run code quality gates for changed code:
  `uv run ruff check addon/src/captive_portal/api/routes/ tests/`,
  `uv run mypy addon/src/captive_portal`,
  `uv run interrogate -vv --fail-under=100 addon/src/captive_portal tests`, and
  `uv run reuse lint`; fix only issues within `guest_portal.py`,
  `guest_authorization/`, tests, or `.aislop/baseline.json`

- [ ] T046 [P] Run `uv run pre-commit run --all-files` and fix hook failures
  without bypassing hooks; if hooks update files automatically, stage the
  changes and rerun the affected checks

- [ ] T047 Run full regression suite `uv run pytest tests/ -v` and confirm no
  guest portal, guest authorization, redirect, security-header, Omada, VLAN,
  CSRF, rate-limiter, or integration regression remains before opening the
  implementation PR

- [ ] T048 In the implementation PR only, mark completed checkboxes in
  `specs/014-guest-portal-decomposition/tasks.md` as a separate documentation
  commit after the functional code commits; do not combine code changes with
  task-completion checkbox updates

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Characterization (Phase 2)**: Depends on Setup completion — BLOCKS all
  production code movement
- **US1 Helper Extraction (Phase 3)**: Depends on Phase 2 green baseline
- **US1 Voucher/Booking Extraction (Phase 4)**: Depends on Phase 3 context and
  helper package
- **US2 Complexity Cleanup (Phase 5)**: Depends on Phase 4 orchestration and
  unchanged characterization tests
- **US3 Review Safety (Phase 6)**: Depends on extracted helpers and tests
- **Polish (Phase 7)**: Depends on all desired implementation phases being
  complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Phase 2 and delivers the behavior-
  preserving decomposition with golden characterization evidence
- **User Story 2 (P2)**: Starts after US1 extraction because complexity findings
  are cleared safely by the decomposition
- **User Story 3 (P3)**: Starts after helper files exist and ensures the result
  remains reviewable and testable

### Within Each Story (TDD Cycle)

1. 🟢 **BASELINE**: Characterization tests pass on current behavior before moves
2. 🔴 **RED**: Helper-boundary tests fail before the helper exists
3. 🟢 **GREEN**: Extract the minimum code needed to pass the helper tests
4. ♻️ **REFACTOR**: Simplify while keeping characterization and helper tests green
5. **CI tests MUST pass before manual testing** (constitution §II)

### Parallel Opportunities

- T003-T014 can run in parallel after T001-T002 because they touch different
  test files and shared normalization helpers
- T016-T020 can run in parallel after the Phase 2 baseline is green
- T021-T025 should be integrated carefully because they all update
  `guest_portal.py`, but helper modules can be implemented in small independent
  slices followed by T026
- T027-T028 can run in parallel; T029-T031 are sequential because voucher and
  booking helpers feed the shared orchestrator
- T033-T038 are sequential where they touch `guest_portal.py` or the complexity
  baseline; T039 validates the whole phase
- T040-T041 can run in parallel; T042-T043 follow once helper ownership is final
- T044-T046 can run in parallel after implementation is complete; T047-T048 are
  final sequential validation and task-list maintenance

---

## Parallel Example: Characterization Baseline

```text
# BASELINE — Launch independent characterization tasks in parallel:
Task T004: "GET form rendering and Omada hidden fields"
Task T005: "Voucher authorization golden behavior"
Task T006: "Booking authorization golden behavior"
Task T008: "MAC extraction priority and error details"
Task T011: "Redirect and open-redirect behavior"

# Gate — run after all characterization tests exist:
Task T015: "Run characterization baseline on current code"
```

## Parallel Example: Helper Boundary Tests

```text
# RED — Launch helper-boundary tests in parallel:
Task T016: "Context grouping tests"
Task T017: "Form helper tests"
Task T018: "MAC helper compatibility tests"
Task T019: "Controller helper tests"
Task T020: "Redirect and error helper tests"

# GREEN — Extract helpers while rerunning characterization:
Task T021: "Create context.py"
Task T022: "Extract form.py"
Task T023: "Extract mac_address.py"
Task T024: "Extract controller.py"
Task T025: "Extract redirects.py and errors.py"
Task T026: "Run unchanged characterization suite"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Characterization baseline (T003-T015) — green on current
   code before any production movement
3. Complete Phase 3: Low-risk helper extraction (T016-T026)
4. Complete Phase 4: Voucher and booking flow extraction (T027-T032)
5. **STOP and VALIDATE**: Run unchanged characterization and targeted guest
   regression tests; all green

### Incremental Delivery

1. Characterization baseline → current behavior pinned
2. Context/form/MAC/controller/redirect/error helpers → low-risk extraction green
3. Voucher and booking helpers → `_process_authorization` becomes orchestration
4. Complexity cleanup → C901/noqa and `aislop` guest findings cleared safely
5. Review safety and polish → helper ownership, full gates, and task maintenance

### TDD Discipline (Constitution §II)

- Characterization tests for existing behavior must pass before refactor; do not
  update expected outputs after decomposition unless the original golden was
  wrong about pre-refactor behavior
- New helper-boundary tests must be written before extracting each helper
- Keep commits atomic; task-list checkbox updates are a separate docs commit in
  the future implementation PR
- Never change `portal_settings_ui.py:110` or unrelated admin/settings code for
  this feature

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
