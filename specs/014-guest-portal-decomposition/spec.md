SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Guest Portal Decomposition

**Feature Branch**: `014-guest-portal-decomposition`
**Created**: 2026-06-28
**Status**: Draft
**Input**: Specify a behavior-preserving decomposition of the oversized guest portal authorization module.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Guest Authorization Behavior (Priority: P1)

A maintainer decomposes the guest authorization code while guests, operators,
and controller integrations observe exactly the same behavior as the current
implementation. The `/guest/authorize` GET and POST routes, `/guest/welcome`,
and `/guest/error` keep the same request fields, response bodies, status codes,
redirect `Location` headers, cookies, security headers, controller calls, and
audit log entries for every currently supported success and failure path.

**Why this priority**: The guest authorization path grants or denies network
access. Any behavior change can lock guests out, authorize the wrong device, or
hide security-relevant audit evidence.

**Independent Test**: Can be fully tested by running characterization tests that
pass against the pre-refactor code, applying the decomposition, and running the
same tests unchanged with deterministic fixtures or explicit normalization for
intentionally dynamic values such as CSRF tokens, timestamps, generated grant
IDs, cookies, and audit timestamps, while proving byte-for-byte equivalence for
all stable externally observable output.

**Acceptance Scenarios**:

1. **Given** the pre-refactor guest portal implementation and the post-refactor
   implementation, **When** a guest requests `/guest/authorize` with any
   supported Omada query parameter combination, **Then** the rendered HTML,
   hidden form fields, CSRF behavior, status code, content type, and security
   headers are equivalent.
2. **Given** the pre-refactor guest portal implementation and the post-refactor
   implementation, **When** a guest submits a valid voucher or booking code by
   GET or POST, **Then** the resulting grant state, controller authorization
   payload, audit log entry, cookie, status code, redirect target, and success
   response are equivalent.
3. **Given** the pre-refactor guest portal implementation and the post-refactor
   implementation, **When** a guest submits an invalid, expired, duplicate,
   VLAN-denied, rate-limited, malformed, or otherwise unauthorized code,
   **Then** the deny decision, HTTP status, sanitized guest-facing error,
   retry link, audit log metadata, and absence or presence of controller calls
   are equivalent.
4. **Given** the pre-refactor guest portal implementation and the post-refactor
   implementation, **When** controller authorization is unavailable, rejected,
   or retry-exhausted, **Then** grant failure state, sanitized guest-facing
   error text, HTTP status, audit log metadata, and diagnostic logging are
   equivalent.

---

### User Story 2 - Clear Complexity Findings Safely (Priority: P2)

A maintainer completes the decomposition so the guest portal code no longer
appears as an isolated complexity hotspot, while preserving the public HTTP and
security contract defined in User Story 1.

**Why this priority**: Issue #172 remains open because the current
`guest_portal.py` file is about 1262 lines, `_process_authorization` is about
546 lines, and the flagged handlers carry too many parameters or C901
suppression risk. Clearing these findings lowers maintenance risk only if it
does not alter the contract.

**Independent Test**: Can be fully tested by running the complexity quality gate
and configured linting after the characterization suite proves behavior is
unchanged.

**Acceptance Scenarios**:

1. **Given** the decomposition is complete, **When** the complexity scanner is
   run, **Then** `complexity/file-too-large` for `guest_portal.py`,
   `complexity/function-too-long` for `_process_authorization`, and the guest
   portal `complexity/too-many-params` findings are cleared or explicitly
   documented if a route signature cannot be changed without contract risk.
2. **Given** the decomposition is complete, **When** configured Python linting is
   run, **Then** the guest authorization handlers pass C901 without `# noqa`
   suppressions on `show_authorize_form` or `_process_authorization`.
3. **Given** a flagged parameter count belongs to a FastAPI route handler whose
   parameters are dictated by query or form fields, **When** the parameter count
   is reduced internally, **Then** all accepted field names, aliases, defaults,
   optionality, and validation behavior remain identical.
4. **Given** reducing a FastAPI route handler parameter count would introduce
   unacceptable request or response contract risk, **When** the implementation is
   reviewed, **Then** that finding may remain documented or baselined instead of
   forcing a risky behavior change.

---

### User Story 3 - Improve Future Review Safety (Priority: P3)

A maintainer reviewing later guest authorization changes can understand and test
small cohesive units instead of one oversized security-critical module, making
future fixes safer and easier to audit.

**Why this priority**: The decomposition is valuable only if it makes future
changes easier to review without scattering behavior across unrelated areas or
weakening the existing safety net.

**Independent Test**: Can be fully tested by inspecting the resulting file scope,
reviewing that extracted units remain directly tied to guest authorization, and
confirming targeted tests identify the behavior protected by each unit.

**Acceptance Scenarios**:

1. **Given** the decomposition is complete, **When** a maintainer reviews the
   guest authorization flow, **Then** voucher validation, booking validation,
   MAC extraction, controller authorization, redirect handling, and error or
   audit behavior are discoverable through cohesive, directly related units.
2. **Given** a future maintainer changes one guest authorization concern,
   **When** they run the related characterization tests, **Then** regressions in
   the observable guest HTTP contract, controller calls, or audit outcomes are
   detected without requiring unrelated feature changes.
3. **Given** the decomposition is complete, **When** the repository quality gates
   run, **Then** test coverage for the guest authorization flow is maintained or
   increased and no constitution quality gate regresses.

---

### Edge Cases

- GET submissions to `/guest/authorize` that include both `code` and
  `csrf_token` MUST continue to enter the authorization flow instead of
  rendering the form.
- GET requests without a complete submission MUST continue to render the form
  and preserve Omada query parameters including `clientMac`, `clientIp`,
  `site`, `apMac`, `gatewayMac`, `radioId`, `ssidName`, `vid`, `t`, and
  `redirectUrl`.
- The hidden field and alias contract for `continue`, `continue_url`,
  `clientMac`, and `client_mac` MUST remain compatible with current GET and
  POST behavior.
- MAC extraction priority MUST remain unchanged across `X-MAC-Address`,
  `X-Client-Mac`, `Client-MAC`, form data, and query parameters, including the
  current tie-break order, normalization of dash-separated Omada MAC addresses,
  and rejection of invalid or missing MACs.
- Booking authorization MUST preserve integration lookup across configured
  integrations, start and end window checks, grace-period handling, duplicate
  grant detection, case-preserved booking references, and integration-specific
  VLAN checks.
- Voucher authorization MUST preserve validation, redemption, status updates,
  device limit handling, duplicate device behavior, expiry handling, and
  voucher-specific VLAN checks.
- Redirect handling MUST preserve safe `continue` destinations, fallback to
  `/guest/welcome`, root-path awareness, and open-redirect protections.
- Error handling MUST continue to sanitize guest-visible messages, preserve
  retry parameters where currently provided, avoid leaking controller internals,
  and render HTML error pages rather than raw JSON for guest flows.
- Controller authorization MUST preserve behavior when no adapter is configured,
  when a legacy site override is valid or invalid, and when controller errors
  transition grants to failed status.
- Debug logging MUST remain redacted for code and CSRF token values and MUST NOT
  expose secrets or sensitive guest authorization details.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The decomposition MUST be behavior-preserving: all stable
  externally observable behavior of `/guest/authorize` GET and POST,
  `/guest/welcome`, and `/guest/error` MUST remain byte-for-byte equivalent for
  the same inputs and repository state, while intentionally dynamic values MUST
  be compared with deterministic fixtures or explicit normalization.
- **FR-002**: Before production code is moved, the current guest authorization
  behavior MUST be pinned by characterization tests that pass against the
  pre-refactor implementation and continue to pass unchanged after the
  decomposition.
- **FR-003**: Characterization coverage MUST include successful voucher
  authorization, successful booking authorization, GET submission behavior,
  POST submission behavior, form rendering, CSRF token generation, CSRF token
  extraction from GET query parameters, POST form data, and the `X-CSRF-Token`
  header, missing, malformed, expired, tampered, and Origin or Referer
  mismatched CSRF failures, MAC extraction, Omada parameter pass-through,
  redirect handling, security headers, sanitized error rendering, controller
  authorization, and controller failure behavior.
- **FR-004**: Authorization and denial decisions MUST remain unchanged for valid
  codes, invalid formats, missing codes, missing or invalid MAC addresses,
  expired vouchers, revoked vouchers, duplicate grants, device-limit failures,
  missing integrations, bookings outside the allowed window, VLAN-denied
  requests, rate-limited clients, and controller errors.
- **FR-005**: Grant persistence MUST remain unchanged, including start and end
  timestamps, status transitions, voucher or booking references, integration
  identifiers, user-input code preservation, Omada metadata truncation, and
  controller grant identifiers.
- **FR-006**: Audit logging MUST remain unchanged for success, denied,
  rate-limited, MAC extraction failure, integration unavailable, VLAN failure,
  and controller failure outcomes, including actor, action, outcome, target
  fields, and metadata keys and values.
- **FR-007**: Controller calls MUST remain unchanged, including whether a call is
  made, adapter selection behavior, legacy site override behavior, payload MAC,
  expiry, gateway MAC, AP MAC, SSID, radio ID, VLAN ID, and handling when no
  controller adapter is configured.
- **FR-008**: The HTTP contract MUST remain unchanged for all guest routes,
  including accepted query parameters, form fields, aliases, default values,
  optionality, validation errors, status codes, headers, cookies, redirect
  `Location` values, response media types, and rendered body content.
- **FR-009**: Security behavior MUST remain unchanged, including CSRF
  validation, rate limiting, trusted proxy client IP handling, open-redirect
  prevention, error sanitization, CSP and other security headers, cache
  controls, referrer policy, cookie attributes, and sensitive value redaction.
- **FR-010**: The oversized `guest_portal.py` module MUST be decomposed into
  cohesive guest-portal units within the guest authorization scope so the guest
  portal `complexity/file-too-large` finding is cleared.
- **FR-011**: `_process_authorization` MUST be decomposed so the guest portal
  `complexity/function-too-long` finding is cleared and C901 passes without a
  `# noqa` suppression on that function.
- **FR-012**: `show_authorize_form` MUST pass C901 without a `# noqa`
  suppression while preserving the GET route contract and current form-rendering
  behavior.
- **FR-013**: Too-many-parameter findings on guest portal handlers SHOULD be
  cleared by internal grouping, dependency composition, or other
  contract-preserving approaches; they MUST NOT be cleared by removing,
  renaming, retyping, or changing accepted HTTP query or form fields.
- **FR-014**: If a FastAPI route handler parameter count cannot be reduced
  without unacceptable risk to the HTTP contract, the remaining finding MUST be
  documented or baselined with the reason and linked to the preserved contract.
- **FR-015**: The scope MUST be limited to `guest_portal.py`, directly extracted
  guest authorization helpers, and tests that characterize or verify the same
  behavior.
- **FR-016**: The decomposition MUST NOT introduce guest-facing features,
  operator-facing configuration changes, database schema changes, controller API
  changes, or unrelated refactors.
- **FR-017**: The deferred `portal_settings_ui.py:110` parameter-count finding
  is out of scope and MUST NOT be addressed as part of this feature.
- **FR-018**: Constitution quality gates MUST remain green, including ruff,
  mypy, interrogate at 100%, tests, REUSE compliance, and the staged complexity
  gate.

### Key Entities

- **Guest Authorization HTTP Contract**: The complete externally observable
  request and response surface for `/guest/authorize`, `/guest/welcome`, and
  `/guest/error`, including fields, headers, cookies, redirects, status codes,
  and rendered content.
- **Authorization Decision**: The allow or deny result for a guest request,
  including the reason, grant state, controller action, audit entry, and
  guest-visible response.
- **Characterization Evidence**: Tests and golden assertions that capture
  current behavior before decomposition and remain unchanged after
  decomposition.
- **Complexity Finding**: A quality-gate result for file size, function length,
  parameter count, or cyclomatic complexity that must be cleared or, only where
  route contract safety requires it, explicitly documented or baselined.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The characterization suite passes against the pre-refactor code
  and passes unchanged after decomposition with no expected-output updates.
- **SC-002**: For all characterized guest authorization scenarios, response
  status, headers, cookies, redirect locations, rendered bodies, audit entries,
  persisted grant fields, and controller call details match the pre-refactor
  behavior exactly.
- **SC-003**: The complexity scanner reports no guest portal
  `complexity/file-too-large` finding, no `_process_authorization`
  `complexity/function-too-long` finding, and no unhandled guest portal
  `complexity/too-many-params` finding.
- **SC-004**: Configured linting reports no C901 violations and no C901 `# noqa`
  suppression remains on `show_authorize_form` or `_process_authorization`.
- **SC-005**: Existing guest portal, guest authorization, Omada, redirect,
  security-header, and integration tests pass with coverage maintained or
  increased.
- **SC-006**: Constitution quality gates for linting, type checking, docstring
  coverage, license compliance, tests, and staged complexity checks pass before
  merge.
- **SC-007**: The implementation PR includes characterization evidence that
  maps each extracted guest authorization unit to the protected behavior and
  test scenario covering it.

## Assumptions

- The current implementation in `addon/src/captive_portal/api/routes/guest_portal.py`
  is the source of truth for behavior that must be preserved.
- Existing guest portal and guest authorization tests provide a substantial
  safety net but may need additional characterization assertions before any code
  movement occurs.
- Clearing the deferred issue #172 guest portal findings is the purpose of the
  future implementation; this specification does not close the issue.
- Grouping FastAPI parameters internally is acceptable only when the public
  query and form contract remains identical.
- No unresolved product questions remain for this specification; the governing
  constraint is behavior-preserving, characterization-first decomposition.
