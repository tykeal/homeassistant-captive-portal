SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0

# Research: Guest Auth Complexity Cleanup

**Feature**: 015-guest-auth-complexity-cleanup
**Date**: 2026-06-29
**Status**: Complete
**Source Basis**: Live `main` source in
`addon/src/captive_portal/api/routes/guest_portal.py`,
`addon/src/captive_portal/api/routes/guest_authorization/context.py`,
`addon/src/captive_portal/api/routes/guest_authorization/bookings.py`,
`addon/src/captive_portal/api/routes/guest_authorization/vouchers.py`,
and the feature-014 guest authorization tests.

## Research Tasks

### R1: Live Complexity Boundary

**Decision**: Treat the current feature-014 decomposition as the starting point
and clear only the remaining guest-authorization findings named in issue #189.

**Rationale**: The live route module already delegates form rendering,
redirects, MAC extraction, controller calls, voucher decisions, booking
decisions, and shared context helpers. The remaining oversized code is now the
shared orchestration body and booking/voucher helper signatures. Moving that
orchestration into `guest_authorization/` and introducing internal context
objects directly addresses the findings while preserving route-visible behavior.

**Alternatives considered**: Rework route signatures with FastAPI models or
custom dependencies. Rejected because it could change query/form aliases,
defaults, validation errors, OpenAPI metadata, or submission behavior.

---

### R2: File Split for `guest_portal.py`

**Decision**: Move `_handle_get_submission`, `_process_authorization`, and the
new private sub-helpers used by `_process_authorization` to
`guest_authorization/orchestration.py`.

**Rationale**: Live `guest_portal.py` is 565 lines. Moving only
`_process_authorization` removes about 148 lines, which is not enough to get
below the 400-line limit. Moving the GET submission dependency resolver as well
removes enough route-internal code while keeping `guest_portal.py` focused on
FastAPI route declarations, template setup, and dependency providers. The moved
GET helper can accept the route dependency-provider callables as arguments so
`orchestration.py` does not import `guest_portal.py` and create a cycle.

**Alternatives considered**: Move welcome/error routes or template setup.
Rejected because those routes are small and unrelated to the complexity
findings. Move controller helpers back into the route module. Rejected because
feature 014 already established the helper package as the safer boundary.

---

### R3: `_process_authorization` Extraction

**Decision**: Keep the public internal entry point small and split the flow into
private helpers with stable responsibilities:

- `_prepare_authorization_flow`: build retry query, validate CSRF, resolve
  trusted-proxy client IP, enforce rate limit, extract MAC, and validate code.
- `_dispatch_authorization_decision`: call voucher or booking helper based on
  `CodeType` and return the existing `AuthorizationDecisionResult`.
- `_finalize_controller_authorization`: apply Omada metadata, apply legacy site
  override, call the existing controller helper, commit, refresh, and update the
  decision grant.
- `_raise_controller_failure`: write the current controller-failure audit entry
  and raise the current 502 message.
- `_complete_success`: clear the rate limiter, audit success, choose the safe
  redirect destination, and build the success redirect response.

**Rationale**: This cuts the 148-line body into reviewable steps without
changing the observable operation order pinned by the guest HTTP contract.

**Alternatives considered**: Combine voucher/booking decisions and controller
finalization into a class. Rejected as a larger architectural change than
needed for a behavior-preserving cleanup.

---

### R4: Shared Decision Context for Voucher and Booking

**Decision**: Add a frozen `GuestDecisionContext` dataclass for branch helpers.
It groups `request`, `audit_service`, `client_ip`, `mac_address`, and `vid`.
`authorize_voucher` and `authorize_booking` will keep `validation_result` and
`session` as explicit arguments and accept `decision_context` as the third
argument.

**Rationale**: Both branch helpers repeat the same audit and request inputs.
Grouping them reduces `authorize_booking` and `authorize_voucher` from seven
parameters to three without changing route signatures, validation behavior, or
dependency lifetimes.

**Alternatives considered**: Store all values on `request.state` and have helper
functions read from it. Rejected because it hides dependencies, makes unit tests
less explicit, and would be harder to type-check.

---

### R5: Booking Grant and Audit Param Objects

**Decision**: Add frozen booking-specific dataclasses:

- `BookingGrantInput` for `mac_address`, `validation_result`, `integration`,
  `booking_identifier`, `start_utc`, `effective_end`, and `now`.
- `BookingAuditContext` for `audit_service`, `request`, `client_ip`,
  `mac_address`, and `validation_result`.
- `BookingAuditFailure` for `error`, `outcome`, `detail`, and optional
  `target_type`.

**Rationale**: `_create_booking_grant` currently has eight parameters and
`_audit_booking_error` has nine. The proposed objects collapse both signatures
well below the six-parameter limit while keeping the existing data visible and
immutable at the helper boundary.

**Alternatives considered**: Replace booking errors with an enum-to-response map
only. Rejected because the audit metadata still needs repeated request context
and target handling; the dataclasses address the actual parameter finding.

---

### R6: Booking Function Split

**Decision**: Split `authorize_booking` into private helpers for integration
lookup, debug logging, VLAN validation/audit, booking window preparation,
duplicate checking, grant creation, and exception-to-HTTP mapping.

**Rationale**: The live `authorize_booking` is 163 lines. Moving coherent blocks
into private helpers lets the entry point remain an orchestration function under
80 lines while preserving exception order and HTTP mappings.

**Alternatives considered**: Move booking logic into `BookingCodeValidator` or a
new service layer. Rejected because this feature is scoped to route helpers and
must not alter broader service responsibilities.

---

### R7: Characterization Reuse Strategy

**Decision**: Reuse feature 014's characterization and regression suite as the
primary before-and-after safety net. Add tests only for extracted units not
already pinned, especially new frozen dataclass methods and helper boundaries
that select audit metadata or controller finalization paths.

**Rationale**: Feature 014 already pins the guest authorization HTTP contract,
redirects, cookies, audit metadata, controller payloads, MAC extraction, Omada
parameter preservation, VLAN behavior, voucher flow, booking flow, CSRF, rate
limiting, and security headers. Reusing those tests prevents expected-output
churn and proves this cleanup is behavior-preserving.

**Alternatives considered**: Write a parallel golden suite from scratch.
Rejected because duplicating feature 014's coverage increases maintenance cost
without improving confidence.

---

### R8: Validation and Quality Gates

**Decision**: Validate implementation with the 014 characterization tests,
focused unit tests for new extracted helpers, guest authorization integration
flows, ruff, mypy, interrogate, REUSE, pre-commit, CI, and the staged aislop
complexity gate.

**Rationale**: The six findings are complexity findings, but they protect
security-sensitive authorization behavior. Both behavior and code-quality gates
must be green before merge.

**Alternatives considered**: Run only the complexity scanner. Rejected because a
passing scanner would not prove byte-equivalent responses, audit entries,
persistence, or controller calls.

## Summary

All research questions are resolved. The implementation should move shared
authorization orchestration into the existing guest-authorization helper package,
use frozen internal dataclasses to reduce repeated parameters, split booking and
controller orchestration into cohesive helpers, and keep feature 014's
characterization suite unchanged except for assertions needed by newly extracted
units.
