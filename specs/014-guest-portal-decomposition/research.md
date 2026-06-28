SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Research: Guest Portal Decomposition

**Feature**: 014-guest-portal-decomposition
**Date**: 2026-06-28
**Status**: Complete
**Source Basis**: Live `main` source and tests in
`addon/src/captive_portal/api/routes/guest_portal.py` and `tests/`.

## Research Tasks

### R1: Behavior-Preserving Boundary

**Decision**: Treat the current `guest_portal.py` implementation as the source
of truth and extract only directly related guest authorization helpers.

**Rationale**: The specification requires zero observable behavior change for
`/guest/authorize` GET and POST, `/guest/welcome`, and `/guest/error`. Current
behavior includes form rendering, hidden fields, HMAC CSRF handling, MAC
extraction, rate limiting, voucher and booking decisions, VLAN checks, grant
persistence, legacy Omada site override, controller authorization, audit logs,
redirects, cookies, security headers, and sanitized error rendering.

**Alternatives considered**: Move guest authorization into generic service
layers. Rejected because this could broaden scope and obscure the HTTP contract.
Change FastAPI route signatures to satisfy parameter-count findings. Rejected
unless characterization proves aliases, defaults, validation, and generated
request behavior are identical.

---

### R2: Characterization-Test Strategy

**Decision**: Add golden/characterization tests before moving production code;
run them unchanged after each extraction phase.

**Rationale**: Existing tests cover important pieces but are not sufficient to
prove byte-equivalent stable output. New characterization evidence must capture
request/response contracts, controller call payloads, audit metadata, grants,
security headers, cookies, redirects, retry links, and sanitized error pages.
Dynamic values are normalized explicitly:

- CSRF tokens: replace generated token values with `<csrf-token>` while still
  asserting extraction from GET query, POST form, and `X-CSRF-Token` header.
- Timestamps: freeze time where possible; otherwise compare normalized
  ISO-8601 placeholders for grant and audit timestamps.
- Grant IDs and cookies: compare cookie name, attributes, status code, and
  redirect behavior while replacing generated IDs with `<grant-id>`.
- Audit timestamps: assert actor/action/outcome/target/meta fields exactly and
  normalize timestamp fields.
- Controller result IDs: use deterministic adapter fakes for stable output.

**Alternatives considered**: Rely only on existing integration tests. Rejected
because they often assert broad success or failure, not exact headers, cookies,
locations, rendered HTML, controller payloads, or audit metadata. Update
goldens after refactor. Rejected because the same expected outputs must pass
before and after decomposition.

---

### R3: Request and Dependency Grouping

**Decision**: Use internal typed grouping for Omada request metadata,
authorization dependencies, and flow state, while preserving FastAPI-visible
route parameters.

**Rationale**: `show_authorize_form`, `handle_authorization`,
`_handle_get_submission`, and `_process_authorization` currently pass many
parameters. Internal grouping can reduce function signatures and improve C901
without changing accepted query parameters or form fields. Route signatures may
remain unchanged if FastAPI alias behavior would otherwise be at risk.

**Alternatives considered**: Replace route parameters with pydantic models or
custom dependencies immediately. Rejected for the plan because FastAPI model and
dependency binding can change validation errors or OpenAPI/request behavior.
Grouping should first happen after route-level parameters are captured.

---

### R4: Module Decomposition

**Decision**: Create a narrow `api/routes/guest_authorization/` package for
extracted helpers.

**Rationale**: This keeps the decomposition close to the current route scope and
avoids unrelated service-layer refactors. The unit map is:

- `context.py`: Omada metadata, dependency bundle, client IP, and retry params.
- `form.py`: GET form context, hidden fields, effective continue, debug
  redaction, and template response setup.
- `mac_address.py`: `_extract_mac_address` priority and validation behavior.
- `vouchers.py`: voucher VLAN validation and redemption flow.
- `bookings.py`: booking integration lookup, window checks, duplicate grant
  checks, and grant creation.
- `controller.py`: `_truncate`, legacy site override, controller authorization,
  grant status transitions, and controller failure detail.
- `redirects.py`: safe continue handling, fallback welcome URL, retry URL, and
  success redirect/cookie construction.
- `errors.py`: sanitized guest-visible messages and reusable audit/error
  metadata helpers.

**Alternatives considered**: Split by technical layers such as repositories,
services, and templates. Rejected because the future implementation must not
change data access patterns or introduce broader architecture changes.

---

### R5: Voucher and Booking Flow Preservation

**Decision**: Extract voucher and booking decision paths as pure orchestration
helpers that receive the existing session/services and return the same grant and
VLAN metadata currently produced inline.

**Rationale**: Voucher behavior must preserve validation, redemption, device
limit, duplicate device, expiry, status updates, and voucher VLAN checks.
Booking behavior must preserve lookup across configured integrations, missing
integration handling, start/end/grace windows, duplicate active grant detection,
case-preserved booking references, user-input preservation, integration IDs,
and booking VLAN checks.

**Alternatives considered**: Replace the inline branches with a new polymorphic
code-strategy abstraction. Rejected for this behavior-preserving refactor
because it changes too much control flow before characterization evidence is in
place.

---

### R6: Controller and Omada Metadata Preservation

**Decision**: Extract controller authorization separately from voucher/booking
decision logic.

**Rationale**: `_authorize_with_controller` has a clear contract: no adapter
marks the grant ACTIVE, configured adapters receive MAC, expiry, gateway MAC,
AP MAC, SSID, radio ID, and VLAN ID, success stores `grant_id`, and
`OmadaClientError` or `OmadaRetryExhaustedError` transitions the grant to
FAILED with diagnostic-only detail. Legacy site override must continue only for
`OmadaLegacyAdapter` and only for valid hex site IDs.

**Alternatives considered**: Inline controller authorization in each code-type
helper. Rejected because it would duplicate grant status, audit, and controller
failure behavior and increase review risk.

---

### R7: Error, Audit, and Redirect Handling

**Decision**: Keep error/audit/redirect behavior explicit and contract-tested
rather than treating it as incidental route plumbing.

**Rationale**: Current behavior includes rate-limit audit metadata, MAC failure
audit entries, denied/error outcomes for each voucher and booking exception,
controller failure audit details, successful grant metadata, root-path-aware
fallbacks, safe continue validation, strict `grant_id` cookies, no-store cache
headers, and `strict-origin` referrer policy. Error pages must continue to
render HTML with sanitized guest-visible text and retry URLs.

**Alternatives considered**: Convert guest errors to JSON or central exception
models. Rejected because the spec explicitly preserves rendered guest HTML error
pages and current HTTP behavior.

---

### R8: Validation and Quality Gates

**Decision**: Use targeted guest characterization and existing suites first,
then run repository quality gates.

**Rationale**: The smallest validation set that covers the changed behavior is
the new characterization suite plus existing tests for guest portal flow,
guest authorization flow, Omada params/errors, external URL/root-path behavior,
post-auth redirects, VLAN authorization, CSRF, rate limiting, security headers,
and guest app routing. Final implementation validation must include ruff, mypy,
interrogate, REUSE, and staged `aislop` complexity checks.

**Alternatives considered**: Run only full test suites after the refactor.
Rejected because failures would be harder to localize and would not prove the
pre-refactor golden baseline.

## Summary

All research decisions are resolved. The future implementation will preserve
the guest HTTP, audit, grant, and controller contracts by first adding golden
characterization coverage, then extracting only guest authorization helpers into
cohesive modules while keeping FastAPI-visible behavior unchanged.
