SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Feature Specification: Guest Auth Complexity Cleanup

**Feature Branch**: `015-guest-auth-complexity-cleanup`
**Created**: 2026-06-29
**Status**: Draft
**Input**: Specify behavior-preserving cleanup of remaining guest-auth complexity findings.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Guest Authorization Behavior (Priority: P1)

A maintainer clears guest authorization complexity findings while guests,
operators, audit consumers, and controller integrations observe exactly the same
behavior as the current implementation. The `/guest/authorize` GET and POST
routes, `/guest/welcome`, and `/guest/error` keep the same request handling,
responses, redirects, headers, cookies, audit entries, grant state changes, and
controller calls for every supported success and failure path.

**Why this priority**: Guest authorization decides whether a device receives
network access. Any observable behavior change can deny valid guests, authorize
invalid devices, hide audit evidence, or alter the Home Assistant and Omada
integration contract.

**Independent Test**: Can be fully tested by reusing the feature-014 guest
authorization characterization suite as the primary safety net, extending it
only where a to-be-extracted unit is not yet pinned, and proving that all stable
observable outputs match before and after cleanup with deterministic fixtures or
explicit normalization for intentionally dynamic values.

**Acceptance Scenarios**:

1. **Given** the current guest authorization implementation and the cleaned-up
   implementation, **When** a guest requests `/guest/authorize` with any
   supported Omada query parameter combination, **Then** the rendered HTML,
   hidden fields, CSRF behavior, status code, media type, security headers, and
   preserved query data are equivalent.
2. **Given** the current guest authorization implementation and the cleaned-up
   implementation, **When** a guest submits a valid voucher or booking code by
   GET or POST, **Then** the grant state, controller authorization payload,
   audit entry, cookie behavior, status code, redirect target, and success
   response are equivalent.
3. **Given** the current guest authorization implementation and the cleaned-up
   implementation, **When** a guest submits an invalid, expired, duplicate,
   VLAN-denied, rate-limited, malformed, missing, or otherwise unauthorized
   code, **Then** the deny decision, HTTP status, sanitized guest-facing error,
   retry behavior, audit metadata, and controller call presence or absence are
   equivalent.
4. **Given** the current guest authorization implementation and the cleaned-up
   implementation, **When** controller authorization is unavailable, rejected,
   or retry-exhausted, **Then** grant failure state, guest-visible error text,
   HTTP status, audit metadata, diagnostic logging, and controller retry
   behavior are equivalent.

---

### User Story 2 - Clear Guest Authorization Findings (Priority: P2)

A maintainer removes the remaining guest authorization complexity findings from
the isolated complexity baseline without changing route signatures or adding new
lint suppressions.

**Why this priority**: The remaining findings are internal helper hotspots left
behind deliberately by feature 014. Clearing them reduces maintenance risk and
moves the project toward a 100/100 aislop score only if the behavior-preserving
contract from User Story 1 remains intact.

**Independent Test**: Can be fully tested by running the characterization suite,
the complexity scanner, and configured quality gates after cleanup and verifying
that the six named findings are absent with no new `# noqa` suppressions.

**Acceptance Scenarios**:

1. **Given** the cleanup is complete, **When** the complexity scanner evaluates
   `guest_portal.py`, **Then** the `complexity/file-too-large` finding is gone
   and the file is below the 400-line limit.
2. **Given** the cleanup is complete, **When** the complexity scanner evaluates
   `_process_authorization` in `guest_portal.py`, **Then** the
   `complexity/function-too-long` finding is gone and the function is at or
   below the 80-line limit.
3. **Given** the cleanup is complete, **When** the complexity scanner evaluates
   `authorize_booking`, `_create_booking_grant`, and `_audit_booking_error` in
   `guest_authorization/bookings.py`, **Then** `authorize_booking` is at or
   below the 80-line limit and all three helpers are at or below the six
   parameter limit.
4. **Given** the cleanup is complete, **When** the complexity scanner evaluates
   `authorize_voucher` in `guest_authorization/vouchers.py`, **Then** the helper
   is at or below the six parameter limit.
5. **Given** the cleanup is complete, **When** linting checks C901 and suppression
   usage, **Then** guest authorization passes without new `# noqa` suppressions.

---

### User Story 3 - Improve Future Review Safety (Priority: P3)

A maintainer reviewing future guest authorization changes can reason about small,
cohesive internal units and their characterization evidence instead of one
oversized flow.

**Why this priority**: The cleanup should make future security-sensitive changes
easier to review and verify while keeping scope limited to guest authorization.

**Independent Test**: Can be fully tested by inspecting the completed cleanup,
its tests, and the refreshed complexity baseline to confirm that changed units
remain within the guest authorization scope and that protected behaviors are
mapped to characterization coverage.

**Acceptance Scenarios**:

1. **Given** the cleanup is complete, **When** a maintainer reviews the guest
   authorization flow, **Then** voucher handling, booking handling, grant
   persistence, auditing, controller authorization, redirects, and error
   outcomes are identifiable in cohesive guest authorization units.
2. **Given** a future maintainer changes a guest authorization concern, **When**
   they run the related characterization tests, **Then** regressions in the
   guest HTTP contract, controller calls, persisted grants, or audit outcomes are
   detected without requiring unrelated feature changes.
3. **Given** the cleanup is complete, **When** the repository quality gates run,
   **Then** coverage is maintained or increased and no constitution quality gate
   regresses.

---

### Edge Cases

- GET submissions to `/guest/authorize` that include both `code` and
  `csrf_token` MUST continue to authorize rather than render a blank form.
- GET requests without a complete submission MUST continue to render the form
  and preserve Omada query parameters, including `clientMac`, `clientIp`,
  `site`, `apMac`, `gatewayMac`, `radioId`, `ssidName`, `vid`, `t`, and
  `redirectUrl`.
- The accepted field and alias behavior for `continue`, `continue_url`,
  `clientMac`, and `client_mac` MUST remain unchanged for GET and POST.
- MAC extraction priority, normalization, validation, and failure behavior MUST
  remain unchanged across supported headers, form fields, and query parameters.
- Booking authorization MUST preserve integration lookup, booking window checks,
  grace-period behavior, duplicate grant detection, case-preserved references,
  and VLAN checks.
- Voucher authorization MUST preserve validation, redemption, status updates,
  device-limit handling, duplicate device behavior, expiry handling, and VLAN
  checks.
- Redirect handling MUST preserve safe `continue` destinations, fallback to
  `/guest/welcome`, root-path awareness, and open-redirect protection.
- Error handling MUST continue to sanitize guest-visible messages, preserve retry
  parameters where currently provided, avoid leaking controller internals, and
  render guest HTML error pages where currently rendered.
- Controller authorization MUST preserve behavior when no adapter is configured,
  when a legacy site override is valid or invalid, and when controller errors
  transition grants to failed status.
- Debug logging MUST remain redacted for codes, CSRF tokens, and other sensitive
  guest authorization details.
- `portal_settings_ui.py:110` is tracked by issue #190 and MUST remain out of
  scope for this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The cleanup MUST be behavior-preserving: all stable externally
  observable behavior of `/guest/authorize` GET and POST, `/guest/welcome`, and
  `/guest/error` MUST remain byte-for-byte equivalent for the same HTTP inputs
  and persistence fixture state, while intentionally dynamic values MUST be
  compared with deterministic fixtures or explicit normalization.
- **FR-002**: The feature-014 guest authorization characterization suite MUST be
  reused as the primary safety net before and after cleanup.
- **FR-003**: The characterization suite MUST cover all to-be-extracted guest
  authorization units before and after cleanup; any unit not already pinned by
  the feature-014 suite MUST have new assertions that pin its behavior.
- **FR-004**: The HTTP contract MUST remain unchanged, including accepted query
  parameters, form fields, aliases, default values, optionality, validation
  behavior, status codes, headers, cookies, redirect `Location` values, response
  media types, and rendered body content.
- **FR-005**: Authorization and denial decisions MUST remain unchanged for valid
  codes, invalid formats, missing codes, missing or invalid MAC addresses,
  expired vouchers, revoked vouchers, duplicate grants, device-limit failures,
  missing integrations, bookings outside allowed windows, VLAN-denied requests,
  rate-limited clients, and controller errors.
- **FR-006**: Grant persistence MUST remain unchanged, including timestamps,
  status transitions, voucher or booking references, integration identifiers,
  submitted code preservation, Omada metadata, and controller grant identifiers.
- **FR-007**: Audit logging MUST remain unchanged for success, denied,
  rate-limited, MAC extraction failure, integration unavailable, VLAN failure,
  and controller failure outcomes, including actor, action, outcome, target
  fields, and metadata keys and values.
- **FR-008**: Controller calls MUST remain unchanged, including whether a call is
  made, adapter selection, legacy site override handling, payload MAC, expiry,
  gateway MAC, AP MAC, SSID, radio ID, VLAN ID, and no-adapter behavior.
- **FR-009**: Security behavior MUST remain unchanged, including CSRF validation,
  rate limiting, trusted proxy client IP handling, open-redirect prevention,
  error sanitization, security headers, cache controls, referrer policy, cookie
  attributes, and sensitive value redaction.
- **FR-010**: `guest_portal.py` MUST no longer trigger
  `complexity/file-too-large`; its line count MUST be below 400.
- **FR-011**: `_process_authorization` in `guest_portal.py` MUST no longer
  trigger `complexity/function-too-long`; its length MUST be at or below 80
  lines.
- **FR-012**: `authorize_booking` in `guest_authorization/bookings.py` MUST no
  longer trigger `complexity/function-too-long` or `complexity/too-many-params`;
  its length MUST be at or below 80 lines and its parameter count MUST be at or
  below six.
- **FR-013**: `_create_booking_grant` in `guest_authorization/bookings.py` MUST
  no longer trigger `complexity/too-many-params`; its parameter count MUST be at
  or below six.
- **FR-014**: `_audit_booking_error` in `guest_authorization/bookings.py` MUST no
  longer trigger `complexity/too-many-params`; its parameter count MUST be at or
  below six.
- **FR-015**: `authorize_voucher` in `guest_authorization/vouchers.py` MUST no
  longer trigger `complexity/too-many-params`; its parameter count MUST be at or
  below six.
- **FR-016**: Parameter-count reductions MUST be achieved only through internal
  helper input grouping, context objects, or function extraction; they MUST NOT
  remove, rename, retype, or alter route query parameters, form fields, aliases,
  defaults, optionality, or validation behavior.
- **FR-017**: The cleanup MUST NOT add new `# noqa` suppressions and MUST keep
  ruff C901 passing for guest authorization code.
- **FR-018**: The implementation scope MUST be limited to `guest_portal.py`, the
  `guest_authorization/` helper package, tests that characterize or verify guest
  authorization behavior, and the refreshed `.aislop` baseline.
- **FR-019**: The cleanup MUST NOT introduce guest-facing features,
  operator-facing configuration changes, database schema changes, controller API
  changes, route signature changes, or unrelated refactors.
- **FR-020**: The deferred `portal_settings_ui.py:110` finding MUST NOT be
  addressed as part of this feature.
- **FR-021**: Constitution quality gates MUST remain green, including ruff, mypy,
  interrogate at 100%, tests, coverage requirements, REUSE compliance, and the
  staged complexity gate.

### Key Entities

- **Guest Authorization HTTP Contract**: The externally observable request and
  response surface for `/guest/authorize`, `/guest/welcome`, and `/guest/error`,
  including fields, headers, cookies, redirects, status codes, and rendered
  content.
- **Authorization Decision**: The allow or deny result for a guest request,
  including reason, grant state, controller action, audit entry, and guest
  response.
- **Characterization Evidence**: Existing feature-014 tests and any required new
  assertions that capture current behavior before cleanup and remain valid after
  cleanup.
- **Complexity Finding**: One of the six named aislop findings for file size,
  function length, or parameter count that this feature must clear.
- **Internal Helper Boundary**: A non-route implementation boundary that may be
  reorganized without changing the guest HTTP contract.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The feature-014 guest authorization characterization suite passes
  before and after cleanup, with new assertions added only for behavior not
  already pinned.
- **SC-002**: For characterized guest authorization scenarios, response status,
  headers, cookies, redirect locations, rendered bodies, audit entries,
  persisted grant fields, and controller call details match current behavior.
- **SC-003**: The complexity scanner reports no `complexity/file-too-large`
  finding for `guest_portal.py`, which is below 400 lines.
- **SC-004**: The complexity scanner reports no `complexity/function-too-long`
  finding for `_process_authorization` or `authorize_booking`, each at or below
  80 lines.
- **SC-005**: The complexity scanner reports no `complexity/too-many-params`
  finding for `authorize_booking`, `_create_booking_grant`,
  `_audit_booking_error`, or `authorize_voucher`, each at or below six
  parameters.
- **SC-006**: Ruff C901 passes for guest authorization code and no new `# noqa`
  suppression is present.
- **SC-007**: Ruff, mypy, interrogate at 100%, tests, coverage checks, REUSE
  checks, and staged complexity checks are green before merge.
- **SC-008**: The six guest authorization findings no longer appear in active
  scan output, and `.aislop/baseline.json` is refreshed to reflect the cleaned
  state, contributing toward a 100/100 aislop score.
- **SC-009**: The final implementation diff is limited to guest authorization
  modules, their characterization or verification tests, and the `.aislop`
  baseline.

## Assumptions

- The current `main` implementation is the source of truth for behavior that
  must be preserved.
- Feature 014 already supplied the guest authorization characterization suite
  intended to protect this cleanup.
- All six issue #189 findings are on internal helper functions or files rather
  than FastAPI route handlers, so they can be reduced without changing route
  signatures.
- The cleanup is a code-quality feature only; product behavior, user interface
  copy, persistence semantics, and controller semantics are intentionally
  unchanged.
- No unresolved product questions remain for this specification; the governing
  constraint is behavior-preserving, characterization-backed cleanup.
